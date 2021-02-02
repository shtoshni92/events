import torch
import torch.nn as nn
import numpy as np

from auto_memory_model.memory.um_rnn import UnboundedRNNMemory
from auto_memory_model.controller.base_controller import BaseController
from coref_utils.utils import get_mention_to_cluster_idx
from pytorch_utils.label_smoothing import LabelSmoothingLoss


class UnboundedRNNMemController(BaseController):
    def __init__(self, new_ent_wt=1.0, over_loss_wt=1.0, event_subtype_loss_wt=1.0, **kwargs):
        super(UnboundedRNNMemController, self).__init__(**kwargs)
        self.new_ent_wt = new_ent_wt
        self.over_loss_wt = over_loss_wt
        self.event_subtype_loss_wt = event_subtype_loss_wt

        self.memory_net = UnboundedRNNMemory(
            hsize=self.ment_emb_to_size_factor[self.ment_emb] * self.hsize + 2 * self.emb_size,
            drop_module=self.drop_module,
            **kwargs)

        # Set loss functions
        self.cross_entropy_fn = nn.CrossEntropyLoss(reduce='sum')
        # self.cross_entropy_fn = nn.CrossEntropyLoss()
        self.bce_fn = nn.BCEWithLogitsLoss()

    @staticmethod
    def get_actions(pred_mentions, clusters):
        # Useful data structures
        mention_to_cluster = get_mention_to_cluster_idx(clusters)

        actions = []
        cell_to_cluster = {}
        cluster_to_cell = {}

        cell_counter = 0
        for mention in pred_mentions:
            if tuple(mention) not in mention_to_cluster:
                # Not a mention
                # (Mention type list, Action list)
                actions.append(None)
            else:
                # Sort by mention types
                cluster_list = sorted(list(mention_to_cluster[tuple(mention)]), key=lambda x: x[0])
                cur_actions = []
                for (ment_type, ment_cluster) in cluster_list:
                    ment_tuple = (mention[0], mention[1], ment_type)
                    if ment_cluster in cluster_to_cell:
                        # Cluster is already being tracked
                        cur_actions.append([cluster_to_cell[ment_cluster], 'c', ment_tuple])
                    else:
                        # Cluster is not being tracked
                        # Add the mention to being tracked
                        cluster_to_cell[ment_cluster] = cell_counter
                        cell_to_cluster[cell_counter] = ment_cluster
                        cur_actions.append([cell_counter, 'o', ment_tuple])
                        cell_counter += 1

                actions.append(cur_actions)

        return actions

    def calculate_coref_loss(self, action_prob_list):
        num_cells = 0
        coref_loss = 0.0
        target_list = []
        total_terms = 0.0

        # First filter the action tuples to sample invalid
        for idx, (coref_new_scores, cell_idx, action_str) in enumerate(action_prob_list):
            gt_idx = None
            if action_str == 'c':
                gt_idx = cell_idx
            elif action_str == 'o':
                # Overwrite
                gt_idx = (1 if num_cells == 0 else num_cells)
                num_cells += 1

            target = torch.tensor([gt_idx]).cuda()
            target_list.append(target)

            weight = torch.ones_like(coref_new_scores).float().cuda()
            weight[-1] = self.new_ent_wt

            label_smoothing_fn = LabelSmoothingLoss(smoothing=0.0, dim=0)
            # loss_fn = nn.CrossEntropyLoss(weight=weight)
            coref_loss += label_smoothing_fn(coref_new_scores, target, weight)
            total_terms += 1

        return coref_loss

    @staticmethod
    def get_event_subtype_loss(type_logit_list, type_list):
        # print(type_logit_list[0])
        type_logit_tens = torch.stack(type_logit_list)
        target = torch.tensor(type_list).cuda()
        event_subtype_loss = nn.CrossEntropyLoss(reduce='sum')(type_logit_tens, target)

        return event_subtype_loss

    def forward(self, example, teacher_forcing=False):
        """
        Encode a batch of excerpts.
        """
        outputs = self.get_mention_embs_and_actions(example)
        ment_pred_loss, pred_mentions, gt_actions, mention_emb_list, mention_score_list = outputs[:5]

        local_emb_list = [None] * len(mention_emb_list)

        follow_gt = self.training or teacher_forcing
        rand_fl_list = np.random.random(len(mention_emb_list))
        if teacher_forcing:
            rand_fl_list = np.zeros_like(rand_fl_list)

        type_logit_list, type_list, action_prob_list, action_list = self.memory_net(
            example, mention_emb_list, local_emb_list, mention_score_list, pred_mentions, gt_actions, rand_fl_list,
            teacher_forcing=teacher_forcing)

        coref_loss = 0.0
        loss = {'total': 0}
        if follow_gt:
            loss['event_subtype'] = self.get_event_subtype_loss(type_logit_list, type_list)
            loss['total'] += loss['event_subtype'] * self.event_subtype_loss_wt

            if len(action_prob_list) > 0:
                coref_loss = self.calculate_coref_loss(action_prob_list)
                loss['coref'] = coref_loss
                loss['total'] += loss['coref']

                if ment_pred_loss is not None:
                    loss['total'] += ment_pred_loss

            return loss, action_list, pred_mentions, gt_actions
        else:
            return coref_loss, action_list, pred_mentions, gt_actions
