# -*- coding: utf-8 -*-
from newspaper import Article
import feedparser
from telegraphapi import Telegraph
import telegram
from telegram.error import *
from mtranslate import translate
import time
import re
import schedule
import datetime
import os
import threading
from postgres import Postgres

#https://devcenter.heroku.com/articles/config-vars#using-foreman-and-heroku-config

TOKEN_ALERT = os.environ['TOKEN_ALERT']
TOKEN_TELEGRAM = os.environ['TOKEN_TELEGRAM']
TELEGRAPH_ACCOUNT = os.environ['TELEGRAPH_ACCOUNT']
MY_CHAT_ID_TELEGRAM = os.environ['MY_CHAT_ID_TELEGRAM']

telegraph = Telegraph()
telegraph.createAccount(TELEGRAPH_ACCOUNT)
 
MY_ITALIAN_READING_PER_MINUTE = os.environ['MY_ITALIAN_READING_PER_MINUTE']
bot = telegram.Bot(TOKEN_TELEGRAM)
chat_id_List = []
allUrl = []
allRssFeed = []

try:
    update_id = bot.getUpdates()[0].update_id
except IndexError:
    update_id = None

def init_DB():
	global STRING_DB
	db = Postgres(STRING_DB)
	db.run("CREATE TABLE IF NOT EXISTS url (id serial PRIMARY KEY, url varchar(100) unique );")       
	db.run("CREATE TABLE IF NOT EXISTS feed (id serial PRIMARY KEY, url varchar(100) unique);")
	db.run("CREATE TABLE IF NOT EXISTS users (id serial PRIMARY KEY, chat_id int unique, name varchar(50), time_added varchar(20));")
	db.close()

def insert_RSS_Feed_DB():
	global STRING_DB
	db = Postgres(STRING_DB)
	url = 'http://www.motorsport-total.com/rss_f1.xml'
	db.run("INSERT INTO feed (url) VALUES ('{}') ON CONFLICT (url) DO NOTHING;".format(url) )
	url = 'http://www.motorsport-total.com/rss_motorrad_MGP.xml'
	db.run("INSERT INTO feed (url) VALUES ('{}') ON CONFLICT (url) DO NOTHING;".format(url) )
	db.close()

def load_RSS_Feed_DB():
	global STRING_DB
	db = Postgres(STRING_DB)
	selectList = db.all("SELECT * FROM feed;" )
	allRssFeed = [item[1] for item in selectList ]
	print("def load_RSS_Feed_DB():")
	print(allRssFeed)
	print("def load_RSS_Feed_DB():")
	db.close()
	
def get_nth_article():
	global STRING_DB
	db = Postgres(STRING_DB)
	selectList =  db.all("SELECT * FROM url;")
	allUrl = [item[1] for item in selectList ]
	for feed in allRssFeed:
		print("parsing entries")
		print(feed)
		entries = feedparser.parse( feed ).entries
		for i in reversed( range(10) ):
			try:
				url = entries[i].link
			except Exception as e:
				print("excp1 ", e)
				continue
			if  url not in allUrl:
				try:
					db.run("INSERT INTO url (url) VALUES ('{}') ON CONFLICT (url) DO NOTHING;".format(url) )
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
				multithreading = 1
				if multithreading:
					threading.Thread(target=sendTelegraph, args=(articleImage, articleTitle, boldArticleContent, articleUrl, string, feed)).start()
				else:
					sendTelegraph( articleImage, articleTitle, boldArticleContent, articleUrl, string, feed )
	db.close()
		
def load_chat_id():
	global chat_id_List
	global STRING_DB
	db = Postgres(STRING_DB)
	selectList = db.all("SELECT chat_id FROM users;")
	chat_id_List = selectList
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
	boldArticleContent = boldArticleContent #+ "."
	articleTitle = articleTitle
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
	
	try:
		#html_content = "<h4><b>" + articleTitle + "</b>" + imageLink + "</h4>" + "<b>" + boldArticleContent + "</b>\n" + "<a href=\"" + articleUrl + "\">LINK</a>\n\n" + string + "\n\n\n" + stringTranslated 
		html_content = '<h4><b>{}</b>{}</h4><b>{}</b>\n<a href="{}">LINK</a>\n\n{}\n\n\n{}'.format(articleTitle,imageLink,boldArticleContent,articleUrl,string,stringTranslated)

	except:
		pass
	stringList = re.split(r"(?<!\w\.\w.)(?<![A-Z][a-z]\.)(?<=\.|\?)\s", stringToBetranslated)
	TOKEN_TRANSLATE = ' 9992362973473279238732489 ' # token che serve per dividere i paragrafi e correttamente associarli ad ogni sua traduzione... non 
	                                                # basta mettere il punto perchè a volte viene tradotto ... con una virgola! 
	                                                # NB spazio numero casuale spazio
	                                                # se non c'è spazio non traduce prima parola (giustamente)
	stringToTranslate = TOKEN_TRANSLATE.join(stringList)
	stringBulkTranslated = translate( stringToTranslate, "en","de" )
	paragraphTranslated = stringBulkTranslated.split(TOKEN_TRANSLATE)
	i = 0
	for paragraph in stringList:
		try:
			html_content = html_content +  '<strong>{}</strong>\n<i>{}</i>\n\n'.format(paragraph,paragraphTranslated[i])
			i = i + 1
		except:
			pass
	html_content = imageLink + html_content
	page = telegraph.createPage( title = articleTitle,  html_content= html_content, author_name="f126ck" )
	url2send = 'http://telegra.ph/' + page['path']
	catIntro = getCategoryIntro( feed )
	
	for chat_id in chat_id_List:
		try:
			bot.sendMessage(parse_mode = "Html", text =  "<a href=\"" + url2send + "\">" + catIntro + "</a>" +  "<b>" + articleTitle + "</b>" + "\n"  + timeReading, chat_id = chat_id)
		except Unauthorized:
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
	db = Postgres(STRING_DB)
	db.run("INSERT INTO users (chat_id,name,time_added) VALUES ('{}','{}','{}') ON CONFLICT (chat_id) DO NOTHING ;".format(MY_CHAT_ID_TELEGRAM, "@f126ck","1503407762") )
	db.close()
	
def main():
	init_DB()
	insert_RSS_Feed_DB()
	load_RSS_Feed_DB()
	load_User_Me()
	load_chat_id()
	schedule.every(20).minutes.do( get_nth_article )
	#start = time.time()
	get_nth_article()
	#end = time.time()
	#print(end - start)
	while True:
		try:
			schedule.run_pending()
		except NetworkError:
			time.sleep(10)
		except Unauthorized:
			update_id += 1
try:
	main()
except Exception as e:
	botALERT = telegram.Bot(TOKEN_ALERT)
	text = "[!] Error:\n<b>{}:{}</b> in DeutschFormel1bot on function ".format( (type(e).__name__), e)
	botALERT.sendMessage(chat_id=MY_CHAT_ID_TELEGRAM, text = text , parse_mode="Html")
