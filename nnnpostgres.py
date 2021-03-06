# -*- coding: utf-8 -*-
#@telegram-bot: @DeutschFormel1Bot
#@author: @f126ck
from newspaper import Article
import feedparser
from telegraphapi import Telegraph
import telegram
from telegram.error import Unauthorized, NetworkError
from mtranslate import translate
import time
import re
import schedule
import datetime
import os
import threading
import traceback
import postgresql
from textblob import TextBlob
import textblob
from textblob import *

STRING_DB = os.environ['DATABASE_URL'].replace("postgres","pq")
TOKEN_ALERT = os.environ['TOKEN_ALERT']
TOKEN_TELEGRAM = os.environ['TOKEN_TELEGRAM']
TELEGRAPH_ACCOUNT = os.environ['TELEGRAPH_ACCOUNT']
MY_CHAT_ID_TELEGRAM = int( os.environ['MY_CHAT_ID_TELEGRAM'] )
bot = telegram.Bot(TOKEN_TELEGRAM)

MY_ITALIAN_READING_PER_MINUTE = 235
telegraph = Telegraph()
telegraph.createAccount(TELEGRAPH_ACCOUNT)
chat_id_List = []

allUrl = []
allRssFeed = []

try:
    update_id = bot.getUpdates()[0].update_id
except IndexError:
    update_id = None

def init_DB():
	global STRING_DB
	db = postgresql.open(STRING_DB)
	ps = db.prepare("CREATE TABLE IF NOT EXISTS url (id serial PRIMARY KEY, url varchar(300) unique, timestamp varchar(20) );")
	ps()          
	ps = db.prepare("CREATE TABLE IF NOT EXISTS feed (id serial PRIMARY KEY, url varchar(100) unique);")
	ps()
	ps = db.prepare("CREATE TABLE IF NOT EXISTS users (id serial PRIMARY KEY, chat_id int unique, name varchar(70), time_added varchar(20));")
	ps()
	db.close()

def insert_RSS_Feed_DB():
	global STRING_DB
	db = postgresql.open(STRING_DB)
	
	url = 'http://www.motorsport-total.com/rss_f1.xml'
	ps = db.prepare("INSERT INTO feed (url) VALUES ('{}') ON CONFLICT (url) DO NOTHING;".format(url) )
	ps()
	
	url = 'http://www.motorsport-total.com/rss_motorrad_MGP.xml'
	ps = db.prepare("INSERT INTO feed (url) VALUES ('{}') ON CONFLICT (url) DO NOTHING;".format(url) )
	ps()
	db.close()
	
def load_RSS_Feed_DB():
	global STRING_DB
	global allRssFeed
	db = postgresql.open(STRING_DB)
	ps = db.prepare("SELECT * FROM feed;")
	allRssFeed = [ item[1] for item in ps() ]
	db.close()
	
def get_nth_article():
	global STRING_DB
	global allRssFeed
	db = postgresql.open(STRING_DB)
	ps = db.prepare("SELECT * FROM url;")
	allUrl = [ item[1] for item in ps() ]
	for feed in allRssFeed:
		entries = feedparser.parse( feed ).entries
		for i in reversed( range(10) ):
			try:
				url = entries[i].link
			except Exception as e:
				print("excp1", e)
				continue
			if  url not in allUrl:
				try:
					timestampNow = round( datetime.datetime.now().timestamp() )
					ps = db.prepare("INSERT INTO url (url,timestamp) VALUES ('{}','{}') ON CONFLICT (url) DO NOTHING;".format(url,timestampNow) )
					ps()
				except Exception as e:
					print("excp1", e)
				article = Article(url)
				article.download()
				article.parse()
				text = article.text
				articleImage = article.top_image
				articleTitle = article.title
				articleUrl = article.url
				string = text
				string = re.sub( r"Zoom © .*[\n]*\(Motorsport-Total\.com\)" , "" , string) # elimina
				string = re.sub( r"[0-9]+\. [A-Za-z]+ [0-9]+ - [0-9]+:[0-9]+ Uhr", "", string ) # elimina data
				boldArticleContent = ""
				######
				#MULTITHREADING
				######
				multithreading = 0
				if multithreading:
					threading.Thread(target=sendTelegraph, args=(articleImage, articleTitle, boldArticleContent, articleUrl, string, feed)).start()
					time.sleep(1) # introduced because telegraphapi.exceptions.TelegraphAPIException: Error while executing createPage: FLOOD_WAIT_3

				else:
					sendTelegraph( articleImage, articleTitle, boldArticleContent, articleUrl, string, feed )		
	db.close()
		
def load_chat_id():
	global chat_id_List
	global STRING_DB
	db = postgresql.open(STRING_DB)
	ps = db.prepare("SELECT * FROM users;")
	chat_id_List = [ item[1] for item in ps() ]
	db.close()
	
def getTimeReadingString( words ):
	lung = len(words)
	minutes = len(words) / MY_ITALIAN_READING_PER_MINUTE
	if minutes == 0:
		return str(lung) + " parole.\n~1 min."
	timeReading = str(lung) + " parole.\n~" + str( int(minutes) )  + " min, " + str( round( (minutes-int(minutes) ) * 60 ) ) + " sec"
	return timeReading

def sendTelegraph( articleImage, articleTitle, boldArticleContent, articleUrl, string ,feed ):
	html_content = ""
	stringAll = ""
	string = string.replace("ANZEIGE","")
	string = string.replace(u'\xa0', u'')
	string = re.sub('\t+', '', string)
	string = re.sub('\t+ ', '', string)
	string = re.sub('\n +\n+ ', '\n', string)
	string = re.sub('<[^<]+?>', '', string)
	string = re.sub('\n+','\n', string).strip().replace(">","")
	string = re.sub('\n +\n', '\n', string)
	
	words = ''.join(c if c.isalnum() else ' ' for c in articleTitle + boldArticleContent + string).split() #http://stackoverflow.com/questions/17507876/trying-to-count-words-in-a-string
	timeReading = getTimeReadingString( words )
	stringToBetranslated = articleTitle + ". " + boldArticleContent + " " + string
	imageLink = '<a href="{}" target="_blank"><img src="{}"></img></a><a href="{}" target="_blank">LINK</a>\n\n'.format(articleImage,articleImage,articleUrl)
	stringList = re.split(r"(?<!\w\.\w.)(?<![A-Z][a-z]\.)(?<=\.|\?)\s", stringToBetranslated)
	i = 0
	lenParagraph = len(stringList)
	for paragraph in stringList:
		try:
			i = i + 1
			blob = TextBlob(paragraph)
			html_content = html_content +  '<strong>[{}/{}]\n{}</strong>\n<i>{}</i>\n\n'.format(i,lenParagraph,paragraph, str( blob.translate(to="en") )   )
			
		except Exception as e:
			print("err building paragraph",e)
			print(articleUrl)
			print(paragraph)
	html_content = imageLink + html_content
	fatto = 0
	tentativo = 0
	while(fatto==0 and tentativo < 6):
		try:
			page = telegraph.createPage( title = articleTitle,  html_content= html_content, author_name="f126ck" )
			fatto = 1
			tentativo = tentativo + 1
		except Exception as e:
			print("error create telegraph",e)
			time.sleep(3)
			fatto = 0
			tentativo = tentativo + 1
	if fatto == 0:
		text = articleUrl
		for chat_id in chat_id_List:
			try:
				bot.sendMessage(parse_mode = "Html", text =  text, chat_id = chat_id)
			except Exception as e:
				print("error sending msg", e)
				continue
		return
	
	url2send = 'http://telegra.ph/' + page['path']
	catIntro = getCategoryIntro( feed )
	for chat_id in chat_id_List:
		try:
			bot.sendMessage(parse_mode = "Html", text =  "<a href=\"" + url2send + "\">" + catIntro + "</a>" +  "<b>" + articleTitle + "</b>" + "\n"  + timeReading, chat_id = chat_id)
		except:
			pass

def getCategoryIntro( feed ):
	category = ""
	if "GP2" in feed.upper():
		category = "GP2"
	if "WEC" in feed.upper():
		category = "WEC"
	if "F1" in feed.upper():
		category = "F1"
	if "MGP" in feed.upper():
		category = "MOTOGP"
	if "FORMELSPORT_FE" in feed.upper():
		category = "FORMULA E"
	if "INDYCAR" in feed.upper():
		category = "INDYCAR"
	if category != "":
		return "[" + category + "]" + "\n"
	else:
		return "LINK"

def load_User_Me():
	global STRING_DB
	global MY_CHAT_ID_TELEGRAM
	db = postgresql.open(STRING_DB)
	ps = db.prepare("INSERT INTO users (chat_id,name,time_added) VALUES ('{}','{}','{}') ON CONFLICT (chat_id) DO NOTHING;".format(MY_CHAT_ID_TELEGRAM,"me","20170821 22:54") )
	ps()
	db.close()
	
def main():
	print("main init db")
	init_DB()
	
	print("rss feed db")
	insert_RSS_Feed_DB()
	
	print("rss feed db")
	load_RSS_Feed_DB()
	
	print("load user me")
	load_User_Me()
	print("load chat id")
	load_chat_id()
	
	print("get article")
	get_nth_article()
	
	print("main schedule")
	schedule.every(20).minutes.do( get_nth_article )
	
	while True:
		try:
			schedule.run_pending()
			time.sleep(10)
		except NetworkError:
			time.sleep(10)
		except Unauthorized:
			update_id += 1
		except Exception as e:
			print("error while true", e)
try:
	main()
except Exception as e:
	print("err ty main", e)
	try:
		botALERT = telegram.Bot(TOKEN_ALERT)
		text = "[!] Error:\n<b>{}:{}</b> in DeutschFormel1bot on function ".format( (type(e).__name__), e)
		botALERT.sendMessage(chat_id=MY_CHAT_ID_TELEGRAM, text = text , parse_mode="Html")
	except Exception as e:
		print("Errore Main ", e)
