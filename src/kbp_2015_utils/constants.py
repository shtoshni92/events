
SPLIT_TO_DIR = {"train": "mod_training", "dev": "mod_dev", "test": "eval"}
SUBDIR_DICT = {"source": "source", "ann": "hopper"}
SUBDIR_EXT = {"source": ".txt", "ann": ".event_hoppers.xml"}


DOC_TYPES = ['multi_post', 'newswire']
DOC_TYPES_TO_IDX = {doc_type: idx for idx, doc_type in enumerate(DOC_TYPES)}


REALIS_VALS = ['actual', 'generic', 'other']
REALIS_VALS_TO_IDX = {realis_val: idx for idx, realis_val in enumerate(REALIS_VALS)}


EVENT_TYPES = ['business', 'conflict', 'contact', 'justice', 'life', 'manufacture', 'movement',
               'personnel', 'transaction']
EVENT_TYPES_TO_IDX = {event_type: idx for idx, event_type in enumerate(EVENT_TYPES)}


EVENT_SUBTYPES = ['business_declarebankruptcy', 'business_endorg', 'business_mergeorg', 'business_startorg',
                  'conflict_attack', 'conflict_demonstrate', 'contact_broadcast', 'contact_contact',
                  'contact_correspondence', 'contact_meet', 'justice_acquit', 'justice_appeal',
                  'justice_arrestjail', 'justice_chargeindict', 'justice_convict', 'justice_execute',
                  'justice_extradite', 'justice_fine', 'justice_pardon', 'justice_releaseparole',
                  'justice_sentence', 'justice_sue', 'justice_trialhearing', 'life_beborn', 'life_die',
                  'life_divorce', 'life_injure', 'life_marry', 'manufacture_artifact',
                  'movement_transportartifact', 'movement_transportperson', 'personnel_elect',
                  'personnel_endposition', 'personnel_nominate', 'personnel_startposition',
                  'transaction_transaction', 'transaction_transfermoney', 'transaction_transferownership']
EVENT_SUBTYPES_TO_IDX = {event_subtype: idx for idx, event_subtype in enumerate(EVENT_SUBTYPES)}

SPEAKER_TAGS = ["[SPEAKER_START]", "[SPEAKER_END]"]


EVENT_SUBTYPES_NAME = [
    'Business_Declare-Bankruptcy', 'Business_End-Org', 'Business_Merge-Org', 'Business_Start-Org',
    'Conflict_Attack', 'Conflict_Demonstrate', 'Contact_Broadcast', 'Contact_Contact',
    'Contact_Correspondence', 'Contact_Meet', 'Justice_Acquit', 'Justice_Appeal',
    'Justice_Arrest-Jail', 'Justice_Charge-Indict', 'Justice_Convict', 'Justice_Execute',
    'Justice_Extradite', 'Justice_Fine', 'Justice_Pardon', 'Justice_Release-Parole',
    'Justice_Sentence', 'Justice_Sue', 'Justice_Trial-Hearing', 'Life_Beborn', 'Life_Die',
    'Life_Divorce', 'Life_Injure', 'Life_Marry', 'Manufacture_Artifact',
    'Movement_Transport-Artifact', 'Movement_Transport-Person', 'Personnel_Elect',
    'Personnel_End-Position', 'Personnel_Nominate', 'Personnel_Start-Position',
    'Transaction_Transaction', 'Transaction_Transfer-Money', 'Transaction_Transfer-Ownership'
]