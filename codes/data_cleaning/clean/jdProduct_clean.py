# -*- encoding:utf-8 -*-
import os
import json
import multiprocessing as mp
import re
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tqdm import tqdm
import argparse
from os import listdir, path
from utils.general_policy import GClean
from utils.special_policy import SpecialPolicies
#from read_xhs_note_data import read_data, read_excel
#from textrank4zh import TextRank4Keyword, TextRank4Sentence
#import regex as re
#from summerizer import truncate_sentence, remove_initial_symbols
#from jieba.analyse import extract_tags
#from emoji import emojize, demojize
from utils.check_black_words import CheckBlackWords
from utils.util import load_list_from_structedTxt,load_set_from_txt
from utils.check_black_words import CheckBlackWords
from utils.clean_headtails_from_content import CleanHeadTailsFromContent

#
_TEXT_LONG_REQUIRED_ = 100

#
_FLUSH_STEPS_NUM_ = 1000

cleaner = GClean(_TEXT_LONG_REQUIRED_)

def step1(text):

    if len(text) < _TEXT_LONG_REQUIRED_:
        return "TooShortSentence", 0, text

    # text_normalization
    cleaned_content = cleaner.text_normalization(text)

    # g0 CleanScript
    cleaned_content = cleaner.clean_script(cleaned_content)

    # g3 EngPeriod2ChinPeriod
    #cleaned_content = re.sub(r'[.*?]', '。', cleaned_content)
    cleaned_content = re.sub(r'([\u4e00-\u9fa5])[.*?]',r'\1。', cleaned_content)

    # g5 FanTi2Simplify
    cleaned_content = re.sub('「', '“', cleaned_content)
    cleaned_content = re.sub('」', '”', cleaned_content)
    cleaned_content = re.sub('【', '[', cleaned_content)
    cleaned_content = re.sub('】', ']', cleaned_content)

    # g10 CleanDuplicationInText
    cleaned_content = cleaner.delete_2repeating_long_patterns(cleaned_content)

    # deleteSpaceBetweenChinese for "豆瓣话题"
    cleaned_content = cleaner.deleteSpaceBetweenChinese(cleaned_content)

    cleaned_content = cleaner.remove_last_sentence_without_endpoint(cleaned_content)

    cleaned_content = cleaner.clean_special_rn(cleaned_content)
    cleaned_content = cleaner.clean_tail(cleaned_content)
    # g24 LongEnough
    if len(cleaned_content) < _TEXT_LONG_REQUIRED_:
        return "TooShortSentence", 0, cleaned_content
    return "", 1, cleaned_content

def step2(text):
    is_sentive,badtext = BadChecker.is_spam_text(text,
        thresh_hold=3,
        black_dataType=["badword","gumble","sex","ads","dirty"])
    if is_sentive:
        return "has_sensitive_words:{}".format(badtext),0,text
    return "",1,text

def step3(text):
    return "",1,text

def clean_title(text):
    # g4 CleanDuplicatedPunctuation, not used for cn-wiki dataset
    cleaned_content = cleaner.clean_deplicate_punc(text)

    # g1 InvalidWords + g22 ChineseLessThan60
    cleaned_content = cleaner.clean_valid(cleaned_content)

    # g2 CleanPunctuationsAtHeadTail
    cleaned_content = cleaner.clean_punct_at_last(cleaned_content)
    cleaned_content = cleaner.clean_punct_at_begin(cleaned_content)

    # g3 EngPeriod2ChinPeriod
    cleaned_content = re.sub(r'([\u4e00-\u9fa5])[.*?]',r'\1。', cleaned_content)

    # g5 FanTi2Simplify
    cleaned_content = re.sub('「', '“', cleaned_content)
    cleaned_content = re.sub('」', '”', cleaned_content)
    cleaned_content = re.sub('【', '[', cleaned_content)
    cleaned_content = re.sub('】', ']', cleaned_content)

    # deleteSpaceBetweenChinese
    cleaned_content = cleaner.deleteSpaceBetweenChinese(cleaned_content)

    cleaned_content = SpecialPolicies.RemoveReference(cleaned_content)
    cleaned_content = SpecialPolicies.RemoveHeadWords(cleaned_content)
    cleaned_content = SpecialPolicies.RemoveSpamFromContent(cleaned_content,
        spam=r"(图片发自简书app|原文地址:|综合网络,如有侵权联系删除。|详细了解可以联系官方qq:咨询！)")
    cleaned_content = SpecialPolicies.RemoveAllReference(cleaned_content)

    return cleaned_content

def controller(args):
    
    check_file = os.path.join(args.dest_path,"done.log")
    if os.path.exists(check_file):
        done_set = load_set_from_txt(check_file)
    else:
        done_set = set()

    files = sorted(listdir(args.source_path))
    for line_no,input_file in tqdm(enumerate(files),total=len(files)):
        input_file = input_file.strip()
        if input_file in done_set: continue
        file_size = os.path.getsize(os.path.join(args.source_path,input_file))
        if len(input_file) < 1 or file_size < 20: continue
        yield (args,input_file)

def make_clean(items):
    args,input_file = items
    
    clean_policy = ""
    clean_status = 0

    good_output_file = os.path.join(args.dest_path,"good",input_file)
    if os.path.exists(good_output_file): os.remove(good_output_file)
    good_fo = open(good_output_file, 'a+', encoding='utf-8')

    bad_output_file = os.path.join(args.dest_path,"bad",input_file)
    if os.path.exists(bad_output_file): os.remove(bad_output_file)
    bad_fo = open(bad_output_file, 'a+', encoding='utf-8')

    fpath = os.path.join(args.source_path,input_file)
    with open(fpath,"r",encoding="utf-8") as f:
        datas = f.readlines()
        for line_no,line in tqdm(enumerate(datas),total=len(datas)):
            line = line.strip()
            if len(line) < 10: continue
            js_dict = json.loads(line)
            content = js_dict["content"].strip()

            # step 1: text normalization
            clean_policy,clean_status,text = step1(content)
            
            js_dict["clean_policy"] = "{}".format(clean_policy if clean_status == 0 else "")
            js_dict["clean_status"] = clean_status
            js_dict["content"] = text
            del js_dict["product"]

            jstr = json.dumps(js_dict, ensure_ascii=False)

            if clean_status == 1: good_fo.write(jstr+"\n")
            else: bad_fo.write(jstr+"\n")
            
            if line_no % _FLUSH_STEPS_NUM_ == 0:
                good_fo.flush()
                bad_fo.flush()
    good_fo.close()
    bad_fo.close()
    return input_file

def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source_path',
                        type=str,
                        default="/data/data_warehouse/llm/llm-data-org.del/cn-wiki2_t2s",
                        help='Directory containing trained actor model')
    parser.add_argument('--dest_path',
                        type=str,
                        default="/data/data_warehouse/llm/clean_data/cn-wiki",
                        help='Directory containing trained actor model')
    parser.add_argument('--dataset_name',
                        type=str,
                        default="",
                        help="")
    parser.add_argument('--num_workers',
                        type=int,
                        default=32,
                        help="")
    args = parser.parse_args()
    return args

if __name__ == '__main__':
    args = parse_args()

    if not os.path.exists(args.dest_path):
        os.makedirs(args.dest_path, exist_ok=True)
    GoodDir = os.path.join(args.dest_path, "good")
    BadDir = os.path.join(args.dest_path, "bad")

    if not os.path.exists(GoodDir):
        os.makedirs(GoodDir, exist_ok=True)
    if not os.path.exists(BadDir):
        os.makedirs(BadDir,exist_ok=True)

    check_file = os.path.join(args.dest_path,"done.log")
    check_fo = open(check_file, 'a+', encoding='utf-8')
   
    pools = mp.Pool(args.num_workers)
    for filed in pools.imap(make_clean, controller(args)):
        check_fo.write(filed+"\n")
        check_fo.flush()
    pools.close()
    check_fo.close()
 
