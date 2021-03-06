import json
import os.path
from utils.eval_metrics import moses_multi_bleu
import glob as glob
import numpy as np
import jsonlines
from tabulate import tabulate
import re
from tqdm import tqdm
import sqlite3
import editdistance
import pprint
pp = pprint.PrettyPrinter(indent=4)


def hasNoNumbers(inputString):
  return not any(char.isdigit() for char in inputString)

def checker_global_ent(e,gold):
  nonumber = hasNoNumbers(e)
  sub_string = True
  for g in gold:
    if(e.lower() in g.lower()):
      sub_string = False
  return sub_string and nonumber

def substringSieve(string_list):
    string_list.sort(key=lambda s: len(s), reverse=True)
    out = []
    for s in string_list:
        if not any([s in o for o in out]):
            out.append(s)
    return out

def compute_prf(pred, gold, global_entity_list):
    TP, FP, FN = 0, 0, 0
    if len(gold)!= 0:
        count = 1
        for g in gold:
            if g.lower() in pred.lower():
                TP += 1
            else:
                FN += 1
        list_FP = []
        for e in list(set(global_entity_list)):
            if e.lower() in pred.lower() and checker_global_ent(e,gold):
                if(e.lower() not in gold):
                    list_FP.append(e)
        FP = len(list(set(substringSieve(list_FP))))
        precision = TP / float(TP+FP) if (TP+FP)!=0 else 0
        recall = TP / float(TP+FN) if (TP+FN)!=0 else 0
        F1 = 2 * precision * recall / float(precision + recall) if (precision+recall)!=0 else 0
    else:
        precision, recall, F1, count = 0, 0, 0, 0
    return F1, count

def get_global_entity_MWOZ():
  with open('data/MultiWOZ_2.1/ontology.json') as f:
      global_entity = json.load(f)
      global_entity_list = []
      for key in global_entity.keys():
          if(key not in ["train-book-people","restaurant-book-people",
                        "hotel-semi-stars","hotel-book-stay","hotel-book-people"]): ## this because are single numeber
            global_entity_list += global_entity[key]

      global_entity_list = list(set(global_entity_list))
  return global_entity_list


def get_entity(KB, sentence):
    list_entity = []
    for e in KB:
        if e.lower() in sentence.lower():
            list_entity.append(e.lower())
    return list_entity



def get_splits(data,test_split,val_split):
    train = {}
    valid = {}
    test  = {}
    for k, v in data.items():
        if(k in test_split):
            test[k] = v
        elif(k in val_split):
            valid[k] = v
        else:
            train[k] = v
    return train, valid, test

def get_dialog_single(gold_json,split_by_single_and_domain):
    test  = {}
    single_index = sum([ idex for n,idex in split_by_single_and_domain.items() if "single" in n and n not in ["police_single","hospital_single"]],[])

    for k, v in gold_json.items():
        if(k.lower() in single_index):
            test[k] = v
    return test

def checkin(ent,li):
    for e in li: 
        if(ent in e):
            return e
        if(editdistance.eval(e, ent)<2):
            return e
    return False


with open('data/MultiWOZ_2.1/ontology.json') as f:
    global_entity = json.load(f)
    ontology = {"train":{},"attraction":{},"hotel":{},"restaurant":{}}
    for key in global_entity.keys():
        if("semi" in key):
            domain,_,slot = key.split("-")
            if(domain in ontology): 
                ontology[domain][slot] = global_entity[key]
                
def to_query(domain, dic, reqt):
    if reqt:
        q = f"SELECT {','.join(reqt)} FROM {domain} where"
    else:
        q = f"SELECT * FROM {domain} where"
    for k,v in dic.items():
        if v == "" or v == "dontcare" or v == 'not mentioned' or v == "don't care" or v == "dont care" or v == "do n't care":
            pass
        else:
            if k == 'leaveAt':
                hour, minute = v.split(":")
                v = int(hour)*60 + int(minute)
                q += f' {k}>{v} and'
            elif k == 'arriveBy':
                hour, minute = v.split(":")
                v = int(hour)*60 + int(minute)
                q += f' {k}<{v} and'
            else:
                q += f' {k}="{v}" and'


    q = q[:-3] ## this just to remove the last AND from the query 
    return q

def align_GPT2(text):
    return text.replace("."," .").replace("?"," ?").replace(","," ,").replace("!"," !").replace("'"," '").replace("  "," ")

conn = sqlite3.connect('data/MWOZ.db')
database = conn.cursor()

dialogue_mwoz = json.load(open("data/MultiWOZ_2.1/data.json"))
test_split = open("data/MultiWOZ_2.1/testListFile.txt","r").read()
val_split = open("data/MultiWOZ_2.1/valListFile.txt","r").read()
split_by_single_and_domain = json.load(open("data/dialogue_by_domain.json"))
_,_,gold_json = get_splits(dialogue_mwoz,test_split,val_split)
# gold_json = get_dialog_single(gold_json,split_by_single_and_domain)

test = json.load(open(f"data/MultiWOZ_2.1/test/all.json")).items() 
entity_KB = get_global_entity_MWOZ()

def score_MWOZ(model,file_to_score):
    genr_json = json.load(open(file_to_score))
    GOLD, GENR, GOLD_API, GENR_API = [], [],[], []
    acc_API = []
    F1_score = []
    F1_domain = {"train":[],"attraction":[],"hotel":[],"restaurant":[],"taxi":[]}
    # F1_API_domain = {"train":[],"hotel":[],"restaurant":[],"taxi":[]}
    total_match = []
    total_success = []
    match_dy_domain = {"train":[],"attraction":[],"hotel":[],"restaurant":[],"taxi":[]}
    success_dy_domain = {"train":[],"attraction":[],"hotel":[],"restaurant":[],"taxi":[]}
    for uuid,v in tqdm(gold_json.items(), total=len(gold_json)):
        if(uuid=="PMUL3907.json"):
            continue
        ## MATCH
        match = {}
        entity_row_match = {}
        for dom, goal in v["goal"].items():
            if dom in ["train","attraction","hotel","restaurant"]:
                if("info" in goal):
                    query = to_query(dom, goal['info'], ["trainId"] if dom == 'train' else ['name'])
                    database.execute(query)
                    all_rows = database.fetchall()
                    if(len(all_rows)>0):
                        entity_row_match[dom] = all_rows
                        match[dom] = 0 

        ## SUCCESS
        success = {}
        entity_row_success = {}
        for dom, goal in v["goal"].items():
            if(goal and 'reqt' in goal):
                goal['reqt'] = [e for e in goal['reqt'] if e in ['phone', 'address', 'postcode']] ## trainId already in match
                if len(goal['reqt'])>0 and dom in ["train","attraction","hotel","restaurant"]:
                    query = to_query(dom, goal['info'], goal['reqt'])
                    database.execute(query)
                    all_rows = database.fetchall()
                    if(len(all_rows)>0):
                        if(dom=="train" and "leaveAt" in goal['reqt']):
                            for i in range(len(all_rows)):
                                all_rows[i] = list(all_rows[i])
                                time = all_rows[i][goal['reqt'].index("leaveAt")]
                                mins=int(time%60)
                                hours=int(time/60)
                                if(len(str(hours)))==1: hours = "0"+str(hours)
                                if(len(str(mins)))==1: mins = "0"+str(mins)
                                all_rows[i][goal['reqt'].index("leaveAt")] = str(hours)+str(mins)
                        if(dom=="train" and "arriveBy" in goal['reqt']):
                            for i in range(len(all_rows)):
                                all_rows[i] = list(all_rows[i])
                                time = all_rows[i][goal['reqt'].index("arriveBy")]
                                mins=int(time%60)
                                hours=int(time/60)
                                if(len(str(hours)))==1: hours = "0"+str(hours)
                                if(len(str(mins)))==1: mins = "0"+str(mins)
                                all_rows[i][goal['reqt'].index("arriveBy")] = str(hours)+str(mins)
                        entity_row_success[dom] = list( list(r) for r in all_rows)
                        success[dom] = 0 

        if("train" in match):
            if("book" not in v["goal"]['train']):
                match["train"] = 1
        gen_sentence = genr_json[uuid.lower()]
        gold_sentence = [v[1]['conversation'] for v in test if v[1]['src']==uuid][0]
        # domain_id = [v[0]["domain"].replace("_single","") for v in test if v[0]['src']==uuid][0]

        for gold in gold_sentence:
            if(gold['spk']=="SYS-API"):
                domain_id = gold['text'].split(" ")[0]
            if(gold['spk']=="API"):
                if(domain_id=="taxi"): 
                    entity_row_success[domain_id] = [[eval(gold['text'])['phone']]]
                    success["taxi"] = 0
                    match["taxi"] = 1
                else:
                    if(len(gold['text'].split())==3):
                        ref,_,_ = gold['text'].split()
                    elif(len(gold['text'].split())==2):
                        ref,_ = gold['text'].split()
                    else:
                        ref = gold['text']
                    
                    if(ref!= "none"):
                        if(domain_id in entity_row_success):
                            for j in range(len(entity_row_success[domain_id])):
                                entity_row_success[domain_id][j].append(ref)
                        else:
                            entity_row_success[domain_id] = [[ref]]
                        success[domain_id] = 0

        gold_sentence = [g for g in gold_sentence if g['spk'] not in ["API","USR"]]
        domain_id = "attraction"
        for gen, gold in zip(gen_sentence,gold_sentence):
            assert gen['spk'] == gold['spk']
            if(gen['spk']=="SYS-API"):
                domain_id = gold['text'].split(" ")[0]

                GOLD_API.append(gold['text'])
                GENR_API.append(gen['text'])
                if(gold["text"].replace(" ","") == gen["text"].replace(" ","")):
                    acc_API.append(1)
                else:
                    acc_API.append(0)
            else:
                GOLD.append(gold['text'])
                GENR.append(align_GPT2(gen['text']))

                F1, count = compute_prf(align_GPT2(gen['text']), gold['entities'][domain_id], entity_KB)
                if(count==1):
                    F1_score.append(F1)
                    F1_domain[domain_id].append(F1)
                # input()
        # input()

        
        # print(entity_row_match)
        # print(match)
        # print()
        # print(entity_row_success)
        # print(success)
        # print()
        # for s in gen_sentence:
        #     print(s)
        # # print(gen_sentence)
        # print()
        match_score = 0
        success_score = 0
        ## match_score 
        for k_dom,v_entities in entity_row_match.items():
            for row_table in v_entities:
                row_table = [e.lower() for e in row_table if e not in ["?","-"]]
                flag = [0 for _ in row_table]
                for idx_c, clmn_val in enumerate(row_table):
                    for sent in gen_sentence:
                        if(sent['spk'] == "SYS"):
                            if(clmn_val.lower() in sent['text'].lower()):
                                flag[idx_c] = 1 
                if(all(flag)): 
                    match[k_dom] = 1

        if(len(match)>0):
            match_score = int(all([int(v)==1 for k,v in match.items()]))
        else: 
            match_score = 1
        


        if(match_score==1):
            for k_dom,v_entities in entity_row_success.items():
                for row_table in v_entities:
                    row_table = [e.lower() for e in row_table if e not in ["?","-"]]
                    flag = [0 for _ in row_table]
                    for idx_c, clmn_val in enumerate(row_table):
                        for sent in gen_sentence:
                            if(sent['spk'] == "SYS"):
                                if(clmn_val.lower() in sent['text'].lower()):
                                    flag[idx_c] = 1 
                    if(all(flag) and match[k_dom]): 
                        success[k_dom] = 1

            if(len(success)>0):
                success_score = int(all([int(v)==1 for k,v in success.items()]))
            else:
                success_score = 1

        # print(match)
        # print(match_score)
        # print(success)
        # print(success_score)
        # print()
        # print()
        # input()
        total_success.append(success_score) 
        # success_dy_domain[domain_id].append(success_score)
        total_match.append(match_score) 
        # match_dy_domain[domain_id].append(match_score)

    MATCH = sum(total_match)/float(len(total_match))
    SUCCESS = sum(total_success)/float(len(total_success))

    # MATCH_BY_DOMAIN = {dom: (sum(arr)/float(len(arr)))*100 for dom, arr in match_dy_domain.items()}
    # SUCCE_BY_DOMAIN = {dom: (sum(arr)/float(len(arr)))*100 for dom, arr in success_dy_domain.items()}
    # MATCH_BY_DOMAIN["ALL"] = MATCH*100
    # SUCCE_BY_DOMAIN["ALL"] = SUCCESS*100
    # MATCH_BY_DOMAIN["Model"] = model
    # SUCCE_BY_DOMAIN["Model"] = model
    BLEU = moses_multi_bleu(np.array(GENR),np.array(GOLD))
    BLEU_API = moses_multi_bleu(np.array(GENR_API),np.array(GOLD_API))
    return {"Model":model,
            "BLEU":BLEU, 
            "MATCH": MATCH *100,
            "SUCCESS": SUCCESS *100,
            "F1":100*np.mean(F1_score), 
            "train":100*np.mean(F1_domain["train"]), 
            "attra":100*np.mean(F1_domain["attraction"]), 
            "hotel":100*np.mean(F1_domain["hotel"]),
            "restu":100*np.mean(F1_domain["restaurant"]),
            "taxi":100*np.mean(F1_domain["taxi"]),
            "BLEU API":BLEU_API,
            "ACC API": 100* np.mean(acc_API),
            # "F1 API":100*np.mean(F1_API_score)
            },None,None


rows = []
rows_match = []
rows_succs = []
for f in glob.glob("runs/*"):
    if("MWOZ" in f and os.path.isfile(f+'/result.json')):
        params = f.replace("MWOZ_SINGLE","MWOZSINGLE").split("/")[1].split("_")

        balance_sampler = False
        if len(params) == 26:
            d_name,model,_,graph,_,adj,_,edge,_,unilm,_,flattenKB,_,hist_L,_,LR,_,epoch,_,wt,_,kb,_,lay,_,balance_sampler = params
        else:
            d_name,model,_,graph,_,adj,_,edge,_,unilm,_,flattenKB,_,hist_L,_,LR,_,epoch,_,wt,_,kb,_,lay = params
            
        if(d_name=="MWOZ"):
            print(f)
            st = model
            st += f" KB={int(kb)}"
            stats, match, succ = score_MWOZ(st,f+'/result.json')
            rows.append(stats)
            rows_match.append(match)
            rows_succs.append(succ)
        # exit()
# rows.append(score_MWOZ("KB0",'results_KB0.json'))
# rows.append(score_MWOZ("KB50",'results_KB50.json'))
print(tabulate(rows,headers="keys",tablefmt='simple',floatfmt=".2f"))
# print(tabulate(rows_match,headers="keys",tablefmt='simple',floatfmt=".2f"))
# print(tabulate(rows_succs,headers="keys",tablefmt='simple',floatfmt=".2f"))