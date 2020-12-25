
def get_mention_model_name(args):
    model_name_suffix = ""
    model_name_suffix += f'{args.dataset}' + "_"
    model_name_suffix += f'{args.doc_proc}' + "_"
    model_name_suffix += 'mlp_' + f'{args.mlp_size}' + '_'
    # model_name_suffix += 'drop_' + f'{args.dropout_rate}' + '_'
    model_name_suffix += 'model_' + f'{args.model_size}' + '_'
    model_name_suffix += 'emb_' + f'{args.ment_emb}' + '_'
    model_name_suffix += 'type_' + ('spanbert' if args.pretrained_bert_dir else 'bert') + '_'
    model_name_suffix += 'segments_' + f'{args.max_training_segments}' + '_'

    # if not args.multitask:
    #     model_name_suffix += 'no_multitask_'

    if args.finetune:
        model_name_suffix += 'ft_'  # + f'{args.ft_lr}'

    if model_name_suffix[-1] == '_':
        model_name_suffix = model_name_suffix[:-1]

    # model_name_suffix += f"_seed_{args.seed}"
    model_name = "ment_" + model_name_suffix
    return model_name
