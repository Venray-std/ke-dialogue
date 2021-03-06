import json
import os.path
import glob as glob
import numpy as np
import jsonlines
from tabulate import tabulate
import re
from tqdm import tqdm
import sqlite3
import editdistance
from collections import defaultdict
import pprint
from itertools import product
from tabulate import tabulate

timepat = re.compile("\d{1,2}[:]\d{1,2}")
pricepat = re.compile("\d{1,3}[.]\d{1,2}")

def insertSpace(token, text):
    sidx = 0
    while True:
        sidx = text.find(token, sidx)
        if sidx == -1:
            break
        if sidx + 1 < len(text) and re.match('[0-9]', text[sidx - 1]) and \
                re.match('[0-9]', text[sidx + 1]):
            sidx += 1
            continue
        if text[sidx - 1] != ' ':
            text = text[:sidx] + ' ' + text[sidx:]
            sidx += 1
        if sidx + len(token) < len(text) and text[sidx + len(token)] != ' ':
            text = text[:sidx + 1] + ' ' + text[sidx + 1:]
        sidx += 1
    return text

def normalize(text):
    # if isinstance(text, int) or isinstance(text, float):
    #     return text

    # lower case every word
    text = text.lower()

    # replace white spaces in front and end
    text = re.sub(r'^\s*|\s*$', '', text)

    # hotel domain pfb30
    text = re.sub(r"b&b", "bed and breakfast", text)
    text = re.sub(r"b and b", "bed and breakfast", text)
    text = re.sub(r"gueshouses", "guesthouse", text)
    text = re.sub(r"guest house", "guesthouse", text)
    text = re.sub(r"rosas bed and breakfast", "rosa s bed and breakfast", text)
    text = re.sub(r"el shaddia guesthouse", "el shaddai", text)
    

    # normalize phone number
    ms = re.findall('\(?(\d{3})\)?[-.\s]?(\d{3})[-.\s]?(\d{4,5})', text)
    if ms:
        sidx = 0
        for m in ms:
            sidx = text.find(m[0], sidx)
            if text[sidx - 1] == '(':
                sidx -= 1
            eidx = text.find(m[-1], sidx) + len(m[-1])
            text = text.replace(text[sidx:eidx], ''.join(m))

    # normalize postcode
    ms = re.findall('([a-z]{1}[\. ]?[a-z]{1}[\. ]?\d{1,2}[, ]+\d{1}[\. ]?[a-z]{1}[\. ]?[a-z]{1}|[a-z]{2}\d{2}[a-z]{2})',
                    text)
    if ms:
        sidx = 0
        for m in ms:
            sidx = text.find(m, sidx)
            eidx = sidx + len(m)
            text = text[:sidx] + re.sub('[,\. ]', '', m) + text[eidx:]

    # weird unicode bug
    text = re.sub(u"(\u2018|\u2019)", "'", text)

    # replace time and and price
    # text = re.sub(timepat, ' [value_time] ', text)
    # text = re.sub(pricepat, ' [value_price] ', text)
    #text = re.sub(pricepat2, '[value_price]', text)

    # replace st.
    text = text.replace(';', ',')
    text = re.sub('$\/', '', text)
    text = text.replace('/', ' and ')

    # replace other special characters
    text = text.replace('-', ' ')
    text = re.sub('[\":\<>@\(\)]', '', text)

    # insert white space before and after tokens:
    for token in ['?', '.', ',', '!']:
        text = insertSpace(token, text)

    # insert white space for 's
    text = insertSpace('\'s', text)

    # replace it's, does't, you'd ... etc
    text = re.sub('^\'', '', text)
    text = re.sub('\'$', '', text)
    text = re.sub('\'\s', ' ', text)
    text = re.sub('\s\'', ' ', text)
    for fromx, tox in replacements:
        text = ' ' + text + ' '
        text = text.replace(fromx, tox)[1:-1]

    # remove multiple spaces
    text = re.sub(' +', ' ', text)

    # concatenate numbers
    tmp = text
    tokens = text.split()
    i = 1
    while i < len(tokens):
        if re.match(u'^\d+$', tokens[i]) and \
                re.match(u'\d+$', tokens[i - 1]):
            tokens[i - 1] += tokens[i]
            del tokens[i]
        else:
            i += 1
    text = ' '.join(tokens)

    return text

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

def substringSieve(string_list):
    string_list.sort(key=lambda s: len(s), reverse=True)
    out = []
    for s in string_list:
        if not any([s in o for o in out]):
            out.append(s)
    return out

def to_query(domain, dic, reqt):
    if reqt:
        q = f"SELECT {','.join(reqt)} FROM {domain} where"
    else:
        q = f"SELECT * FROM {domain} where"
    for k,v in dic.items():
        # if v == "swimmingpool": v = "swimming pool"
        # if v == "nightclub": v = "night club"
        # if v == "the golden curry": v = "golden curry"
        # if v == "mutliple sports": v = "multiple sports"
        # if v == "the cambridge chop house": v = "cambridge chop house"
        # if v == "the fitzwilliam museum": v = "fitzwilliam museum"
        # if v == "the good luck chinese food takeaway": v = "good luck chinese food takeaway"
        # if v == "the cherry hinton village centre": v = "cherry hinton village centre"
        # if v == "the copper kettle": v = "copper kettle"
        # if v == "pizza express Fen Ditton": v = "pizza express"
        # if v == "shiraz restaurant": v = "shiraz"
        # # if v == "christ's college": v = "christ college"
        # if v == "good luck chinese food takeaway": v = "chinese"

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

def convert_time_int_to_time(all_rows,clmn):#leaveAt_id,arriveBy_id):
    leaveAt_id = -1
    arriveBy_id = -1
    if('leaveAt' in clmn):
        leaveAt_id = clmn.index('leaveAt')
    if('arriveBy' in clmn):
        arriveBy_id = clmn.index('arriveBy')
    if(leaveAt_id!= -1):
        for i in range(len(all_rows)):
            all_rows[i] = list(all_rows[i])
            time = all_rows[i][leaveAt_id]
            mins=int(time%60)
            hours=int(time/60)
            if(len(str(hours)))==1: hours = "0"+str(hours)
            if(len(str(mins)))==1: mins = "0"+str(mins)
            all_rows[i][leaveAt_id] = str(hours)+str(mins)
    if(arriveBy_id!= -1):
        for i in range(len(all_rows)):
            all_rows[i] = list(all_rows[i])
            time = all_rows[i][arriveBy_id]
            mins=int(time%60)
            hours=int(time/60)
            if(len(str(hours)))==1: hours = "0"+str(hours)
            if(len(str(mins)))==1: mins = "0"+str(mins)
            all_rows[i][arriveBy_id] = str(hours)+str(mins)
    return all_rows

def parse_results(dic_data,semi,domain):
    book_query = str(domain)
    if(domain == "taxi"):
        for k, t in semi.items():
            if k in ["leaveAt","destination","departure","arriveBy"]:
                book_query += f" {k} = '{normalize(t)}'"

    if(domain == "hotel"):
        if dic_data["day"]== "" or dic_data["stay"]== "" or dic_data["people"]== "":
            return None,None
    results = None
    if(len(dic_data['booked'])>0):
        if(domain == "train" and 'trainID' in dic_data['booked'][0]):
            book_query += f" trainID = '{normalize(dic_data['booked'][0]['trainID'])}'"
            results =  dic_data['booked'][0]['reference']
        elif(domain != "taxi" and 'name' in dic_data['booked'][0]):
            book_query += f" name = '{normalize(dic_data['booked'][0]['name'])}'"
            results =  dic_data['booked'][0]['reference']
        else:
            results =  dic_data['booked'][0]
    elif(domain == "hotel" and semi['name']!="not mentioned"):
        book_query += f" name = '{normalize(semi['name'])}'"

    for k, t in dic_data.items():
        if(k != 'booked'):
            book_query += f" {k} = '{normalize(t)}'"

    return book_query, results

def get_booking_query(text):
    domain = {"global":set(),"train":[],"attraction":[],"hotel":[],"restaurant":[],"taxi":[],
              "police":[],"hospital":[],"generic":[]}
    domain[text.split()[0]] = re.findall(r"'(.*?)'", text)

    domain["global"] = dict(domain["global"])

    return domain

def get_name(conv,dict_delex):
    for conv_turn in reversed(conv):
        if "name" in dict_delex.keys():
            for ids_v, v in enumerate(r_delex_dictionary["name"]):
                if(v in conv_turn["text"]):
                    return v, ids_v
                if(v.replace("the ","") in conv_turn["text"]):
                    return v, ids_v
    return None, None

def get_start_end_ACT(ACT):
    dic = {}
    mapper = {"one":1,"two":2,"three":3,"3-star":3,"four":4,"five":5}
    for span in ACT:
        if(span[1]=="Stars"):
            if(span[2] in mapper.keys()):
                dic[mapper[span[2]]] = [span[3],span[4]]
            else:
                dic[span[2]] = [span[3],span[4]]
    return dic

def check_metadata(dic, state):
    for d, v in dic.items():
        if (state[d]==0 or state[d]!= v['book']['booked']):
            if (len(v['book']['booked']) > 0):
                state[d] = v['book']['booked']
                return parse_results(v['book'],v['semi'],d), state 
            for k, v1 in v['book'].items():
                if(k != 'booked' and v1 != ""):
                    return parse_results(v['book'],v['semi'],d), state
    return (None, None), state

def get_domain_entity(act):
    domain = {"global":set(),"train":[],"attraction":[],"hotel":[],"restaurant":[],"taxi":[],
              "police":[],"hospital":[],"generic":[]}
    booking_entities = []
    for k,v in act.items():
        if(k.split("-")[0].lower() in domain.keys()):
            for val in v:
                if(val and val[1]!="?" and val[1]!= 'none'):
                    domain[k.split("-")[0].lower()].append(val[1])
        else:
            if k == "Booking-Book" or k == "OfferBooked" or "Booked" in k or "Book"in k:
                for val in v:
                    if(val and val[1]!="?" and val[1]!= 'none'):
                        booking_entities.append(val[1])
    domain["global"] = dict(domain["global"])
    return domain, booking_entities

def get_entity_by_type(domain, info,clmn,post_fix="-info"):
    ### get goal information
    query = to_query(domain, info, clmn)
    database.execute(query)
    all_rows = database.fetchall()
    all_rows = convert_time_int_to_time(all_rows,clmn)
    entity_by_type = {c+post_fix:set() for c in clmn}
    for rows in all_rows:
        for i,c in enumerate(clmn):
            entity_by_type[c+post_fix].add(rows[i])
    # entity_by_type["number_of_options"] = [len(all_rows)]
    return entity_by_type

fin = open("mapping.pair","r")
replacements = []
for line in fin.readlines():
    tok_from, tok_to = line.replace('\n', '').split('\t')
    replacements.append((' ' + tok_from + ' ', ' ' + tok_to + ' '))

pp = pprint.PrettyPrinter(indent=4)
conn = sqlite3.connect('MWOZ.db')
database = conn.cursor()

dialogue_mwoz = json.load(open("MultiWOZ_2.1/data.json"))
test_split = open("MultiWOZ_2.1/testListFile.txt","r").read()
val_split = open("MultiWOZ_2.1/valListFile.txt","r").read()
train, valid, test = get_splits(dialogue_mwoz,test_split,val_split)
split_by_single_and_domain = json.load(open("MultiWOZ_2.1/dialogue_by_domain.json"))

# domains = ["attraction", "hospital", "hotel", "police", "restaurant", "taxi", "train"]
domains = ["attraction", "hotel", "restaurant", "taxi", "train", "all"]

# create directories
print("create directories")
for out in ["train", "valid", "test"]:
    path = "MultiWOZ_2.1/{}/".format(out)
    if not os.path.exists(path):
        os.makedirs(path)

stats = {"all":{}}
for domain in domains:
    if domain != "all":
        domain_single = domain + "_single"
        stats[domain_single] = {}

for i, dataset in enumerate([train, valid, test]):
    out = ""
    if i == 0: out = "train"
    elif i == 1: out = "valid"
    else: out = "test"
    print("generate:", out)

    domain = ""
    
    conversations = {"all":{}}
    for domain in domains:
        if domain != "all":
            domain_single = domain + "_single"
        conversations[domain_single] = {}

    for k, dial in dataset.items():
        for domain in domains:
            if domain != "all":
                domain_single = domain + "_single"

                if not k.lower() in split_by_single_and_domain[domain_single]:
                    continue
            else:
                domain_single = "all"

            conversation = []
            state = {"train":0, "attraction":0, "hotel":0, "restaurant":0, "hospital":0, "police":0, "taxi":0, "bus":0}
            for turns in dial["log"]:
                text_delex = normalize(turns['text'])
                if(turns['metadata']):
                    if out == "test":
                        entities_by_domain, booking_entities = get_domain_entity(turns["dialog_act"])
                    else:
                        entities_by_domain = {"global":dict(),"train":[],"attraction":[],"hotel":[],"restaurant":[],"taxi":[],
                            "police":[],"hospital":[],"generic":[]}
                        booking_entities = []
                    
                    (book, results), state = check_metadata(turns['metadata'],state)
                    if(book):
                        entities_by_domain_book = get_booking_query(book)
                        book_delex = book

                        conversation.append({ "spk": "SYS-API", "entities": entities_by_domain_book, "text": book })
                        dom_API = book.split()[0] ## first token is the API domain
                        ## THIS IS A SIMULATION OF AN API RESULTS
                        if("dialog_act" in turns and dom_API == "train" and "Train-OfferBooked" in turns["dialog_act"]):
                            for elem_ in turns["dialog_act"]["Train-OfferBooked"]:
                                if(elem_[0]=="Ticket" and elem_[1] != "None"):
                                    results = str(results)
                                    results += " " + str(elem_[1])
                        if(domain_single == "taxi_single"):
                            if isinstance(results, dict):
                                str_results = ""
                                for val in results.values():
                                    if str_results != "":
                                        str_results += " "
                                    str_results += val
                                results = str_results

                        entities_by_domain[dom_API] = list(set(entities_by_domain[dom_API]+booking_entities))
                        conversation.append({"spk": "API", "text": str(results).lower()})

                    conversation.append({"spk": "SYS", "entities":entities_by_domain, "text": normalize(turns['text'])})
                else:
                    conversation.append({"spk": "USR", "text": normalize(turns['text'])})

            conversations[domain_single][len(conversations[domain_single]) + 1] = { "domain": domain_single, "conversation": conversation, "src": k }

    print(conversations.keys())
    all_conversations = []
    for key in conversations:
        for idx in conversations[key]:
            all_conversations.append(conversations[key][idx])

        stats[key][out] = len(conversations[key])
        path = "MultiWOZ_2.1/{}/{}.json".format(out, key)
        print("saving", key, path, len(conversations[key]))
        with open(path, "w") as outfile: 
            json.dump(conversations[key], outfile, indent=4)

    dict_conversations = {}
    for conv in all_conversations:
        dict_conversations[len(dict_conversations) + 1] = conv
    path = "MultiWOZ_2.1/{}_data.json".format(out)
    with open(path, "w") as outfile:
        json.dump(dict_conversations, outfile, indent=4)
    print("saving", path, len(all_conversations))

# print
tab = []
for key in stats:
    tab.append([key, stats[key]["train"], stats[key]["valid"], stats[key]["test"]])

print(tabulate(tab, headers=["domain", "train", "valid", "test"], tablefmt='orgtbl'))