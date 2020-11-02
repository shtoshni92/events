import os
import re
import sys
import json
from collections import OrderedDict
import xml.etree.ElementTree as ET
import truecase
from cleantext import clean

from os import path
from transformers import BertTokenizer
from data_processing.utils import get_ent_info, get_clusters_from_xml
import argparse
from red_utils.constants import ELEM_TYPE_TO_IDX, DUPLICATE_START_TAG, DUPLICATE_END_TAG

BERT_RE = re.compile(r'## *')
NEWLINE_TOKEN = "[NEWL]"


class DocumentState(object):
    def __init__(self, key):
        self.doc_key = key
        self.sentence_end = []
        self.token_end = []
        self.tokens = []
        self.subtokens = []
        self.info = []
        self.segments = []
        self.subtoken_map = []
        self.segment_subtoken_map = []
        self.sentence_map = []
        self.segment_info = []
        self.clusters = []

    def finalize(self, clusters, ent_id_to_info):
        # populate clusters
        processed_ent_ids = set()
        for cluster in clusters:
            cur_cluster = []
            for ent_id in cluster:
                processed_ent_ids.add(ent_id)
                cur_cluster.append((ent_id_to_info[ent_id][0], ent_id_to_info[ent_id][1],
                                    ELEM_TYPE_TO_IDX[ent_id_to_info[ent_id][2]]))
            self.clusters.append(cur_cluster)

        for ent_id, info in ent_id_to_info.items():
            if ent_id in processed_ent_ids:
                continue
            else:
                singleton_cluster = [(info[0], info[1], ELEM_TYPE_TO_IDX[info[2]])]
                self.clusters.append(singleton_cluster)

        all_mentions = flatten(self.clusters)
        sentence_map = get_sentence_map(self.segments, self.sentence_end)
        subtoken_map = flatten(self.segment_subtoken_map)
        assert len(all_mentions) == len(set(all_mentions))
        num_words = len(flatten(self.segments))
        assert num_words == len(subtoken_map), (num_words, len(subtoken_map))
        assert num_words == len(sentence_map), (num_words, len(sentence_map))
        return {
            "doc_key": self.doc_key,
            "sentences": self.segments,
            "clusters": self.clusters,
            'sentence_map': sentence_map,
            "subtoken_map": subtoken_map,
        }


def flatten(l):
    return [item for sublist in l for item in sublist]


def split_into_segments(document_state, max_segment_len, constraints1, constraints2):
    current = 0
    while current < len(document_state.subtokens):
        end = min(current + max_segment_len - 1 - 2,
                  len(document_state.subtokens) - 1)
        while end >= current and not constraints1[end]:
            end -= 1
        if end < current:
            end = min(current + max_segment_len - 1 - 2,
                      len(document_state.subtokens) - 1)
            while end >= current and not constraints2[end]:
                end -= 1
            if end < current:
                raise Exception("Can't find valid segment")
        document_state.segments.append(document_state.subtokens[current:end + 1])
        subtoken_map = document_state.subtoken_map[current: end + 1]
        document_state.segment_subtoken_map.append(subtoken_map)
        current = end + 1


def get_sentence_map(segments, sentence_end):
    current = 0
    sent_map = []
    sent_end_idx = 0
    assert len(sentence_end) == sum([len(s) for s in segments])
    for segment in segments:
        for i in range(len(segment)):
            sent_map.append(current)
            current += int(sentence_end[sent_end_idx])
            sent_end_idx += 1
    return sent_map


def get_document(doc_name, tokenized_doc, clusters, ent_id_to_info, segment_len):
    document_state = DocumentState(doc_name)
    word_idx = -1
    for idx, token in enumerate(tokenized_doc):
        if token == NEWLINE_TOKEN:
            # [NEWL] corresponds to "\n" in real doc
            document_state.sentence_end[-1] = True
            continue

        if not BERT_RE.match(token):
            word_idx += 1

        document_state.tokens.append(token)
        # Subtoken and token are same
        document_state.subtokens.append(token)
        if idx == len(tokenized_doc) - 1:
            # End of document
            document_state.token_end += ([True])
        else:
            next_token = tokenized_doc[idx + 1]
            if BERT_RE.match(next_token):
                # If the next token has ## at the start then the current subtoken
                # is clearly not the end of the token
                document_state.token_end += ([False])
            else:
                document_state.token_end += ([True])

        document_state.sentence_end.append(False)
        document_state.subtoken_map.append(word_idx)
    # Last word in the document is obviously end of sentence
    document_state.sentence_end[-1] = True
    split_into_segments(document_state, segment_len,
                        document_state.sentence_end, document_state.token_end)
    document = document_state.finalize(clusters, ent_id_to_info)
    return document


def get_context(tokenizer, tokenized_doc):
    newline_idx = None
    for idx in range(len(tokenized_doc) - 1, -1, -1):
        if tokenized_doc[idx] == NEWLINE_TOKEN:
            newline_idx = idx
            break

    if newline_idx:
        context = tokenized_doc[newline_idx + 1: ]
    else:
        context = tokenized_doc[0: ]

    # Don't add more than 10 tokens in context
    if len(context) > 20:
        context = context[-20:]

    context_str = tokenizer.convert_tokens_to_string(context)
    return context_str


def count_upper_case_chars(string):
    count = 0
    for char in string:
        if char.isupper():
            count += 1

    return count


def tokenize_span(span, doc_name, tokenizer, use_truecase=False, context=None):
    span = span.strip()
    if span == '':
        return [], 0

    span = span.replace("\n", "<N>")
    if use_truecase:
        if (span.upper() == span) or ("proxy" in doc_name):
            # Only do it for all uppercase

            just_trucase_span = truecase.get_true_case(span)
            cand1 = just_trucase_span

            truecase_span_len = len(just_trucase_span)
            context_str = get_context(tokenizer, context)
            input_str = context_str + " " + span
            truecase_context_span = truecase.get_true_case(input_str)
            cand2 = truecase_context_span[-truecase_span_len:]

            if cand1.lower() == cand2.lower():
                # Both options work, choose the option with least number of uppercase characters
                span = cand1 if (count_upper_case_chars(cand1) <= count_upper_case_chars(cand2)) else cand2
                # Weird Truecase error - "when Hindustan" becomes "When HINDUSTAN"
            else:
                span = cand1

    span = span.replace("<N>", NEWLINE_TOKEN)
    newline_count = span.count(NEWLINE_TOKEN)

    tokenized_span = tokenizer.tokenize(span)

    if "[UNK]" in tokenized_span:
        # Try cleaning the text and reprocess
        cleaned_span = clean(span, lower=False)
        tokenized_span = tokenizer.tokenize(cleaned_span)

    # tokenized_span = [token for token in tokenized_span if token != '[UNK]']
    return tokenized_span, newline_count


def tokenize_doc(doc_name, tokenizer, source_file, annotation_file, use_truecase=False, add_duplicate_tag=False):
    # Read the source document
    doc_str = "".join(open(source_file).readlines())
    # altered_doc_str = doc_str.replace("\n", "[NEWL]")

    # Parse the XML
    tree = ET.parse(annotation_file)
    root = tree.getroot()

    # Get entity and cluster information from the annotation file
    ent_map, ent_list = get_ent_info(root, get_duplicates=True)
    clusters = get_clusters_from_xml(root, ent_map)

    tokenized_doc = []
    token_counter = 0
    char_offset = 0  # Till what point has the document been processed
    ent_id_to_info = OrderedDict()

    real_span_to_tokenized_span = {}
    char_to_tokenized_idx = {}
    for (span_start, span_end), ent_type, ent_id in ent_list:
        # Tokenize the string before the span and after the last span
        real_span = tuple([span_start, span_end])
        if real_span not in real_span_to_tokenized_span:
            if char_offset > span_start:
                # Overlapping span
                relv_tokens = tokenizer.tokenize(doc_str[span_start: span_end])

                if span_start in char_to_tokenized_idx:
                    # The shorted span has already been processed! "x" "x y" overlap
                    counter_idx, token_idx = char_to_tokenized_idx[span_start]
                    remaining_tokens, newline_count = tokenize_span(doc_str[char_offset: span_end], doc_name, tokenizer,
                                                                    use_truecase=use_truecase, context=tokenized_doc)
                    tokenized_doc.extend(remaining_tokens)
                    char_offset = span_end
                    # Don't count newline tokens as they will ultimately be removed.
                    token_counter += len(remaining_tokens) - newline_count
                    char_to_tokenized_idx[char_offset] = len(tokenized_doc) - 1

                    ent_id_to_info[ent_id] = tuple([counter_idx, counter_idx + len(relv_tokens) - 1, ent_type])

                elif span_end in char_to_tokenized_idx:
                    # The span has already been processed! "x y" "y" overlap
                    counter_idx, token_idx = char_to_tokenized_idx[span_end]
                    proc_tokens = tokenized_doc[token_idx - len(relv_tokens): token_idx]

                    assert(relv_tokens == proc_tokens)
                    ent_id_to_info[ent_id] = tuple([counter_idx - len(relv_tokens), counter_idx - 1, ent_type])
                else:
                    # We are at lord's mercy
                    print("JESUS")
                    raise ValueError(doc_name)
            else:
                before_span_str = doc_str[char_offset: span_start]
                before_span_tokens, newline_count = tokenize_span(before_span_str, doc_name, tokenizer,
                                                                  use_truecase=use_truecase, context=tokenized_doc)
                tokenized_doc.extend(before_span_tokens)

                # Don't count newline tokens as they will ultimately be removed.
                token_counter += len(before_span_tokens) - newline_count
                char_to_tokenized_idx[span_start] = (token_counter, len(tokenized_doc))

                # Tokenize the span
                span_tokens, newline_count = tokenize_span(doc_str[span_start: span_end], doc_name, tokenizer,
                                                           use_truecase=use_truecase, context=tokenized_doc)

                if ent_type != 'DUPLICATE':
                    ent_id_to_info[ent_id] = tuple([
                        token_counter, token_counter + len(span_tokens) - 1, ent_type])
                else:
                    if add_duplicate_tag:
                        span_tokens = [DUPLICATE_START_TAG] + span_tokens + [DUPLICATE_END_TAG]

                real_span_to_tokenized_span[real_span] = tuple(
                    [token_counter, token_counter + len(span_tokens) - 1])

                tokenized_doc.extend(span_tokens)
                char_offset = span_end
                # Don't count newline tokens as they will ultimately be removed.
                token_counter += len(span_tokens) - newline_count
                char_to_tokenized_idx[char_offset] = (token_counter, len(tokenized_doc))
        else:
            tokenized_start, tokenized_end = real_span_to_tokenized_span[real_span]
            ent_id_to_info[ent_id] = tuple([tokenized_start, tokenized_end, ent_type])

    # Add the tokens after the last span
    rem_doc = doc_str[char_offset:]
    rem_tokens, newline_count = tokenize_span(rem_doc, doc_name, tokenizer, use_truecase=use_truecase,
                                              context=tokenized_doc)
    # Don't count newline tokens as they will ultimately be removed.
    token_counter += len(rem_tokens) - newline_count

    tokenized_doc.extend(rem_tokens)
    return tokenized_doc, ent_id_to_info, clusters


def minimize_partition(split, tokenizer, args, seg_len):
    split_list_file = path.join(args.doc_dir, f'{split}.txt')
    split_files = set([file_name.strip() for file_name in open(split_list_file).readlines()])

    source_files, annotation_files = [], []
    for split_file in split_files:
        source_files.append(path.join(args.source_dir, split_file))
        annotation_files.append(path.join(args.ann_dir, split_file) + ".RED-Relation.gold.completed.xml")

    output_path = path.join(args.output_dir, "{}.{}.jsonlines".format(split, seg_len))
    count = 0

    print("Minimizing {}".format(split))
    with open(output_path, "w") as output_file:
        for doc_name, source_file, annotation_file in \
                zip(split_files, source_files, annotation_files):
            tokenized_doc, ent_id_to_info, clusters = tokenize_doc(
                doc_name, tokenizer, source_file, annotation_file,
                use_truecase=args.use_truecase, add_duplicate_tag=args.add_duplicate_tag)
            document = get_document(doc_name, tokenized_doc, clusters, ent_id_to_info, seg_len)
            output_file.write(json.dumps(document))
            output_file.write("\n")
            count += 1
    print("Wrote {} documents to {}".format(count, output_path))


def minimize_split(args, seg_len):
    tokenizer = BertTokenizer.from_pretrained('bert-base-cased')
    tokenizer.add_special_tokens(
        {'additional_special_tokens': [NEWLINE_TOKEN, DUPLICATE_START_TAG, DUPLICATE_END_TAG]})
    for split in ["dev", "test", "train"]:
        minimize_partition(split, tokenizer, args, seg_len)


if __name__ == "__main__":
    input_dir = sys.argv[1]

    parser = argparse.ArgumentParser()
    parser.add_argument("input_dir", type=str, help="Input directory root")
    parser.add_argument("output_dir", type=str, help="Output directory")
    parser.add_argument("-use_truecase", default=True, action="store_true",
                        help="Pass all documents through truecase.")
    parser.add_argument("-add_duplicate_tag", default=False, action="store_true",
                        help="Add duplicate tag to indicate duplicated text.")

    parsed_args = parser.parse_args()

    parsed_args.source_dir = path.join(parsed_args.input_dir, "data/source")
    parsed_args.ann_dir = path.join(parsed_args.input_dir, "data/mod_annotation")
    parsed_args.doc_dir = path.join(parsed_args.input_dir, "docs")

    if not os.path.isdir(parsed_args.output_dir):
        os.mkdir(parsed_args.output_dir)
    for seg_len in [512]:
        minimize_split(parsed_args, seg_len)
