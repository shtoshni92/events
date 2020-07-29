import torch
import torch.nn as nn
from pytorch_utils.modules import MLP
import math

LOG2 = math.log(2)


class BaseMemory(nn.Module):
    def __init__(self, hsize=300, mlp_size=200, mlp_depth=1, coref_mlp_depth=1,
                 mem_size=None, drop_module=None, emb_size=20, entity_rep='max',
                 use_last_mention=False,
                 **kwargs):
        super(BaseMemory, self).__init__()
        # self.query_mlp = query_mlp
        self.hsize = hsize
        self.mem_size = (mem_size if mem_size is not None else hsize)
        self.mlp_size = mlp_size
        self.mlp_depth = mlp_depth
        self.emb_size = emb_size
        self.entity_rep = entity_rep

        self.drop_module = drop_module

        self.action_str_to_idx = {'c': 0, 'o': 1, 'i': 2, '<s>': 3}
        self.action_idx_to_str = ['c', 'o', 'i']

        self.doc_type_to_idx = {'deft': 0, 'pilot': 1, 'proxy': 2}

        self.use_last_mention = use_last_mention

        if self.entity_rep == 'lstm':
            self.mem_rnn = nn.LSTMCell(
                input_size=self.mem_size,
                hidden_size=self.mem_size)
        elif self.entity_rep == 'gru':
            self.mem_rnn = nn.GRUCell(
                input_size=self.mem_size,
                hidden_size=self.mem_size)

        # CHANGE THIS PART
        self.query_projector = nn.Linear(self.hsize + 4 * self.emb_size, self.mem_size)

        self.mem_coref_mlp = MLP(3 * self.mem_size + 2 * self.emb_size, self.mlp_size, 1,
                                 num_hidden_layers=coref_mlp_depth, bias=True, drop_module=drop_module)
        if self.use_last_mention:
            self.ment_coref_mlp = MLP(3 * self.mem_size, self.mlp_size, 1,
                                      num_hidden_layers=mlp_depth, bias=True, drop_module=drop_module)
        self.ment_type_emb = nn.Embedding(2, self.emb_size)
        self.doc_type_emb = nn.Embedding(3, self.emb_size)
        self.last_action_emb = nn.Embedding(4, self.emb_size)
        self.distance_embeddings = nn.Embedding(11, self.emb_size)
        self.width_embeddings = nn.Embedding(30, self.emb_size)
        self.counter_embeddings = nn.Embedding(11, self.emb_size)

    @staticmethod
    def get_distance_bucket(distances):
        logspace_idx = torch.floor(torch.log(distances.float()) / LOG2).long() + 3
        use_identity = (distances <= 4).long()
        combined_idx = use_identity * distances + (1 - use_identity) * logspace_idx
        return torch.clamp(combined_idx, 0, 9)

    @staticmethod
    def get_counter_bucket(count):
        logspace_idx = torch.floor(torch.log(count.float()) / LOG2).long() + 3
        use_identity = (count <= 4).long()
        combined_idx = use_identity * count + (1 - use_identity) * logspace_idx
        return torch.clamp(combined_idx, 0, 9)

    @staticmethod
    def get_mention_width_bucket(width):
        if width < 29:
            return width

        return 29

    def get_distance_emb(self, distance):
        distance_tens = self.get_distance_bucket(distance)
        distance_embs = self.distance_embeddings(distance_tens)
        return distance_embs

    def get_counter_emb(self, ent_counter):
        counter_buckets = [self.get_counter_bucket(ent_count) for ent_count in ent_counter]
        counter_tens = torch.tensor(counter_buckets).long().cuda()
        counter_embs = self.counter_embeddings(counter_tens)
        return counter_embs

    def get_last_action_emb(self, action_str):
        action_emb = self.action_str_to_idx[action_str]
        return self.last_action_emb(torch.tensor(action_emb).cuda())

    @staticmethod
    def get_coref_mask(ent_counter):
        cell_mask = (ent_counter > 0.0).float().cuda()
        return cell_mask

    def get_coref_new_log_prob(self, query_vector, mem_vectors, last_ment_vectors,
                               ent_counter, distance_embs, counter_embs):
        # Repeat the query vector for comparison against all cells
        num_cells = mem_vectors.shape[0]
        rep_query_vector = query_vector.repeat(num_cells, 1)  # M x H

        # Coref Score
        pair_vec = torch.cat([mem_vectors, rep_query_vector, mem_vectors * rep_query_vector,
                              distance_embs, counter_embs], dim=-1)
        pair_score = self.mem_coref_mlp(pair_vec)
        coref_score = torch.squeeze(pair_score, dim=-1)  # M

        if self.use_last_mention:
            last_ment_vec = torch.cat(
                [last_ment_vectors, rep_query_vector,
                 last_ment_vectors * rep_query_vector], dim=-1)
            last_ment_score = torch.squeeze(self.ment_coref_mlp(last_ment_vec), dim=-1)
            coref_score = coref_score + last_ment_score  # M

        coref_new_mask = torch.cat([self.get_coref_mask(ent_counter), torch.tensor([1.0]).cuda()], dim=0)
        coref_new_scores = torch.cat(([coref_score, torch.tensor([0.0]).cuda()]), dim=0)

        coref_new_scores = coref_new_scores * coref_new_mask + (1 - coref_new_mask) * (-1e4)
        coref_new_log_prob = torch.nn.functional.log_softmax(coref_new_scores, dim=0)
        return coref_new_scores, coref_new_log_prob

    def forward(self, mention_emb_list, actions, mentions, teacher_forcing=False):
        pass