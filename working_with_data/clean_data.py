import subprocess
import nltk
import pandas as pd
from pymongo import MongoClient
from nltk.corpus import stopwords
from string import printable
from sklearn.feature_extraction.text import TfidfVectorizer
from nltk.tokenize import word_tokenize
from sys import argv
import pickle
from nltk.tokenize import RegexpTokenizer
from nltk.stem.wordnet import WordNetLemmatizer
from dateutil import parser
import datetime
from bs4 import BeautifulSoup
import requests
from unidecode import unidecode
import matplotlib.pyplot as plt
import re


# Sites we're working with
# url_names = ['cnn', 'abc', 'fox', 'nyt', 'ap', 'reuters', 'wapo', 'economist', 'huffpo', 'esquire', 'rollingstone', 'cbs', '538', 'vox', 'time', 'slate', 'washtimes']
# These sites are strictly political (doesn't get rid of much data as those sites didn't have many articles)
url_names = ['cnn', 'abc', 'fox', 'nyt', 'reuters', 'wapo', 'huffpo', 'esquire', 'rollingstone', 'cbs', '538', 'washtimes']
words_to_remove = ['http', 'com', '_', '__', '___']


# Remove stop words and lemmatize
def get_processed_text(article_text):
    quotes1 = ' '.join(re.findall('“.*?”', article_text))
    quotes2 = ' '.join(re.findall('".*?"', article_text))
    quotes = quotes1 + quotes2

    tweets = ' '.join(re.findall('\n\n.*?@', article_text))+' '+' '.join(re.findall('\n\n@.*?@', article_text))

    article_text = re.sub('\n\n.*?@', '', article_text)
    article_text = re.sub('\n\n@.*?@', '', article_text)
    # Remove tweet
    article_text = ' '.join([word for word in article_text.split(' ') if not word.startswith('(@') and not word.startswith('http')])

    article_text = re.sub('“.*?”', '', article_text)
    article_text = re.sub('".*?"', '', article_text)

    tokenizer = RegexpTokenizer(r'\w+')
    # create English stop words list
    sw = set(stopwords.words('english'))
    wordnet = WordNetLemmatizer()

    article_text = article_text.lower()
    quotes = quotes.lower()
    tweets = tweets.lower()

    article_text_tokens = tokenizer.tokenize(article_text)
    quotes_tokens = tokenizer.tokenize(quotes)
    tweets_tokens = tokenizer.tokenize(tweets)

    # remove stop words, unwanted words, tweet handles, links from tokens
    article_text_stopped_tokens = [i for i in article_text_tokens if i not in sw and i not in words_to_remove]
    quotes_stopped_tokens = [i for i in quotes_tokens if not i in sw and i not in words_to_remove]
    tweets_stopped_tokens = [i for i in tweets_tokens if not i in sw and i not in words_to_remove]

    # stem token
    article_text = " ".join([wordnet.lemmatize(i) for i in article_text_stopped_tokens])
    quotes = " ".join([wordnet.lemmatize(i) for i in quotes_stopped_tokens])
    tweets = " ".join([wordnet.lemmatize(i) for i in tweets_stopped_tokens])

    return article_text, quotes, tweets


def get_df(db_name):
    client = MongoClient()
    db = client[db_name]

    collection_names = db.collection_names()
    my_collection_names = [name for name in collection_names]

    df = pd.DataFrame(columns=['article_text', 'author', 'date_published', 'headline', 'url', 'processed_text', 'processed_quote', 'processed_tweet', 'source'])
    for collection_name in my_collection_names:
        if collection_name != 'system.indexes':
            site = [name for name in url_names if collection_name.startswith(name)]
            if len(site) != 0:
                site = site[0]
                print('Working on '+collection_name)
                for article in db[collection_name].find():
                    # remove article that just have videos
                    # remove powerpost articles from wapo becaue they are 4000+ words
                    if 'video' not in article['url'] and 'powerpost' not in article['url']:
                        try:
                            url = article['url']
                            source = site
                            headline = article['headline']
                            date_published = article['date_published']
                            author = article['author']
                            article_text = article['article_text']
                            processed_text, processed_quote, processed_tweet = get_processed_text(article_text)
                            # check is quote is nan
                            if type(processed_quote) == float:
                                processed_quote = ''
                            # df.append(pd.Series([article_text, author, date_published, headline, url, processed_text, source]), ignore_index=True)
                            df.loc[-1] = [article_text, author, date_published, headline, url, processed_text, processed_quote, processed_tweet, source]  # adding a row
                            df.index = df.index + 1  # shifting index
                            df = df.sort()  # sorting by index
                        except:
                            print('Problem with article in '+site)
    return df

def get_article_length_hist(df):
    site_article_length = {source: [] for source in df['source'].unique()}
    for source in df['source'].unique():
        new_df = df[df['source'] == source]
        for article in new_df['article_text']:
            site_article_length[source].append(len(article.split()))


    for i, source in enumerate(site_article_length.keys()):
        plt.subplot(4,3,i+1)
        plt.hist(site_article_length[source], normed=True)
        plt.title('Article Length '+source)
    plt.subplots_adjust(hspace=0.4, wspace=0.4)
    plt.show()

def parse_str(x):
    if isinstance(x, str):
        return unidecode(x)
    else:
        return str(x)

# This goes through every cnn article and uses BeautifulSoup to get text instead of newspaper
def fix_cnn(db_name):
    client = MongoClient()
    db = client[db_name]

    collection_names = db.collection_names()
    my_collection_names = [name for name in collection_names if name.startswith('cnn')]

    for collection_name in my_collection_names:
        for article in db[collection_name].find():
            try:
                url = article['url']
                result = requests.get(url)
                soup = BeautifulSoup(result.content, 'html.parser')

                tag1 = soup.find('div', attrs={'class': 'el__leafmedia el__leafmedia--sourced-paragraph'}).text
                tag2 = soup.find_all('div', attrs={'class': 'zn-body__paragraph speakable'})
                tag3 = soup.find_all('div', attrs={'class': 'zn-body__paragraph'})
                new_article_text = tag1+' /n '+parse_str(' \n '.join([line.text for line in tag2]))+parse_str(' \n '.join([line.text for line in tag3]))
                db[collection_name].update_one({
                          '_id': article['_id']
                        },{
                          '$set': {
                            'article_text': new_article_text
                          }
                        }, upsert=False)
            except:
                print('Problem with article! Removing!')
                print(url)
                db[collection_name].remove({"url": url})


# This goes through every huffpo article and uses BeautifulSoup to get text instead of newspaper
def fix_huffpo(db_name):
    client = MongoClient()
    db = client[db_name]

    collection_names = db.collection_names()
    my_collection_names = [name for name in collection_names if name.startswith('cnn')]

    for collection_name in my_collection_names:
        for article in db[collection_name].find():
            try:
                url = article['url']
                result = requests.get(url)
                soup = BeautifulSoup(result.content, 'html.parser')

                tag = soup.find_all('div', attrs={'class': 'content-list-component bn-content-list-text text'})
                new_article_text = parse_str(' \n '.join([line.text for line in tag]))
                db[collection_name].update_one({
                          '_id': article['_id']
                        },{
                          '$set': {
                            'article_text': new_article_text
                          }
                        }, upsert=False)
            except:
                print('Problem with article! Removing!')
                print(url)
                db[collection_name].remove({"url": url})


def clean_df(df):
    # Remove duplicates by url
    df = df.drop_duplicates(subset='url')
    # Below I get rid of large articles that could throw off my algorithms
    # Remove two article types that were very long
    # any url with speech was just a transcript of speeches
    df = df[(df['source'] != 'ap') & (df['source'] != 'economist') & (df['source'] != 'vox') & (df['source'] != 'time') & (df['source'] != 'slate')]

    df[df['source'] == 'wapo'] = df[(df['source'] == 'wapo') & (df['url'].str.contains('powerpost') == False) & (df['url'].str.contains('-speech-') == False)]
    df[df['source'] == 'economist'] = df[(df['source'] == 'economist') & (df['url'].str.contains('transcript') == False)]
    df[df['source'] == 'fox'] = df[(df['source'] == 'fox') & (df['article_text'].str.contains('Want FOX News Halftime Report in your inbox every day?') == False)]
    df[df['source'] == 'esquire'] = df[(df['source'] == 'esquire') & (df['url'].str.contains('-gallery-') == False)]

    # Can't have null values in text
    df = df[pd.notnull(df['processed_text'])]
    df = df.dropna(how='all')
    return df

if __name__ == '__main__':
    # takes in mongo database name and if you want to restore as arg
    db_name, restore = argv[1]


    # Find minimum date in csv so we know where to start
    # df_prev = pd.read_csv('../data/'+str(db_name)+'_data.csv', parse_dates=False, index_col=0)
    # df_prev['date_published'] = df_prev['date_published'].apply(lambda x: parser.parse(x.split('|')[0]))
    # min_date_saved = min(df_prev['date_published']).to_pydatetime()
    #
    # min_date = datetime.date(2017, 5, 13)
    # while min_date > min_date_saved:
    #     min_date -= datetime.timedelta(days=7)
    # print(min_date)
    '''
    df = pd.read_csv('../data/'+str(db_name)+'_data.csv', parse_dates=False)
    get_article_length_hist(df)
    # df = clean_cnn(df)
    df = df[(df['url'].str.contains('powerpost') == False) & (df['url'].str.contains('-speech-') == False)]
    get_article_length_hist(df)
    df.to_csv('../data/'+str(db_name)+'_data.csv', index=False)
    '''

    df = get_df(db_name)
    df = df.drop_duplicates(subset='url')
    # Fix CNN articles that only grabbed the Highlights
    df = fix_cnn(df)
    # Below I get rid of large articles that could throw off my algorithms
    # Remove two article types that were very long
    # any url with speech was just a transcript of speeches
    df = df[(df['source'] != 'ap') & (df['source'] != 'economist') & (df['source'] != 'vox') & (df['source'] != 'time') & (df['source'] != 'slate')]

    df[df['source'] == 'wapo'] = df[(df['source'] == 'wapo') & (df['url'].str.contains('powerpost') == False) & (df['url'].str.contains('-speech-') == False)]
    df[df['source'] == 'economist'] = df[(df['source'] == 'economist') & (df['url'].str.contains('transcript') == False)]
    df[df['source'] == 'fox'] = df[(df['source'] == 'fox') & (df['article_text'].str.contains('Want FOX News Halftime Report in your inbox every day?') == False)]
    df = df.dropna(how='all')
    df.to_csv('../data/'+str(db_name)+'_data.csv', index=False)

    new_df = df[df['source'] == '538']
    urls = []
    articles = []
    processeds = []
    for article, url, processed in zip(new_df['article_text'], new_df['url'], new_df['processed_text']):
        if len(article.split()) > 4000:
            urls.append(url)
            articles.append(article)
            processeds.append(processed)


    # for site in url_names:
    #     print(site+': '+str(len(site_dict[site].keys())))

    # for site in url_names:
    #     for url in site_dict[site].keys():
    #         if site_dict[site][url]['date_published'] == None:
    #             print(site+' date: None')
    #         else:
    #             print(site+' date: '+str(site_dict[site][url]['date_published']))
    #
    # with open('../pickles/site_dict.pkl', 'wb') as f:
    #     pickle.dump(site_dict, f, pickle.HIGHEST_PROTOCOL)
