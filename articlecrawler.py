from time import sleep
from bs4 import BeautifulSoup
from exceptions import *
from multiprocessing import Process
from articleparser import ArticleParser
import os
import calendar
import re
import requests
import pymongo
import urllib.request
import settings

class ArticleCrawler(object):
    def __init__(self):
        self.parser = ArticleParser()
        self.category = {'정치': 100, '경제': 101, '사회': 102, '생활문화': 103,'세계':104, 'IT과학': 105}
        self.selected_category = []
        self.date = {'start_year': 0, 'end_year': 0, 'end_month': 0}

    def set_category(self, *args):
        for key in args:
            if self.category.get(key) is None:
                raise InvalidCategory(key)
            else:
                self.selected_category = args

    def set_date_range(self, start_year, end_year, end_month):
        args = [start_year, end_year, end_month]
        if start_year > end_year:
            raise InvalidYear(start_year, end_year)
        if end_month < 1 or end_month > 12:
            raise InvalidMonth(end_month)
        for key, date in zip(self.date, args):
            self.date[key] = date
        print(self.date)

    def make_news_page_url(self, category_url, start_year, last_year, start_month, last_month):
        maked_url = []
        final_startmonth = start_month
        final_lastmonth = last_month
        for year in range(start_year, last_year + 1):
            if year != last_year:
                start_month = 1
                last_month = 12
            else:
                start_month = final_startmonth
                last_month = final_lastmonth
            for month in range(start_month, last_month + 1):
                for month_day in range(1, calendar.monthrange(year, month)[1] + 1):
                    url = category_url
                    if len(str(month)) == 1:
                        month = "0" + str(month)
                    if len(str(month_day)) == 1:
                        month_day = "0" + str(month_day)
                    url = url + str(year) + str(month) + str(month_day)
                    final_url = url  # page 날짜 정보만 있고 page 정보가 없는 url 임시 저장

                    # totalpage는 네이버 페이지 구조를 이용해서 page=1000으로 지정해 totalpage를 알아냄
                    # page=1000을 입력할 경우 페이지가 존재하지 않기 때문에 page=totalpage로 이동 됨
                    totalpage = self.parser.find_news_totalpage(final_url + "&page=1000")
                    for page in range(1, totalpage + 1):
                        url = final_url  # url page 초기화
                        url = url + "&page=" + str(page)
                        maked_url.append(url)
        return maked_url

    def crawling(self, category_name):
        # MultiThread PID
        print(category_name + " PID: " + str(os.getpid()))

        # 안되면 울거다
        file_name = 'Article_'+str(self.category[category_name])
        conn = pymongo.MongoClient('mongodb://%s:%s@%s:%s/'%(settings.MONGODB_USERID,settings.MONGODB_PASSWORD,settings.MONGODB_HOST,settings.MONGODB_PORT))
        db = conn.get_database(settings.MONGODB_DATABASE)
        collection = db[file_name]

        # 기사 URL 형식
        url = "http://news.naver.com/main/list.nhn?mode=LSD&mid=sec&sid1=" + str(
            self.category.get(category_name)) + "&date="
        # start_year년 1월 ~ end_year의 end_mpnth 날짜까지 기사를 수집합니다.
        final_urlday = self.make_news_page_url(url, self.date['start_year'], self.date['end_year'], 1,
                                               self.date['end_month'])
        print(category_name + " Urls are generated")
        print(final_urlday)
        print(len(final_urlday))
        print("크롤링 시작")
        for URL in final_urlday:

            regex = re.compile("date=(\d+)")
            news_date = regex.findall(URL)[0]

            request = requests.get(URL)
            document = BeautifulSoup(request.content, 'html.parser')
            tag_document = document.find_all('dt', {'class': 'photo'})

            post = []
            row = 0
            for tag in tag_document:
                post.append(tag.a.get('href'))  # 해당되는 page에서 모든 기사들의 URL을 post 리스트에 넣음

            for content_url in post:  # 기사 URL
                # 크롤링 대기 시간
                sleep(0.01)
                # 기사 HTML 가져옴
                request_content = requests.get(content_url)
                document_content = BeautifulSoup(request_content.content, 'html.parser')


                # 기사 제목 가져옴
                tag_headline = document_content.find_all('h3', {'id': 'articleTitle'}, {'class': 'tts_head'})
                text_headline = ''  # 뉴스 기사 제목 초기화
                text_headline = text_headline + self.parser.clear_headline(str(tag_headline[0].find_all(text=True)))
                if not text_headline:  # 공백일 경우 기사 제외 처리
                    continue
                    # 기사 본문 가져옴
                tag_content = document_content.find_all('div', {'id': 'articleBodyContents'})
                text_sentence = ''  # 뉴스 기사 본문 초기화
                text_sentence = text_sentence + self.parser.clear_content(str(tag_content[0].find_all(text=True)))
                if not text_sentence:  # 공백일 경우 기사 제외 처리
                    continue

                # 기사 언론사 가져옴
                tag_company = document_content.find_all('meta', {'property': 'me2:category1'})
                text_company = ''  # 언론사 초기화
                text_company = text_company + str(tag_company[0].get('content'))
                if not text_company:  # 공백일 경우 기사 제외 처리
                    continue

                tag_image = document_content.find_all('span', {'class': 'end_photo_org'})
                image_url = ''  # 이미지 초기화
                image_url = image_url + str(tag_image[0].find('img')['src'])
                image_path = "images/"+file_name+"_"+str(row)+"_"+str(news_date)+'.png'
                urllib.request.urlretrieve(image_url, image_path)
                row = row + 1
                if not image_url:  # 공백일 경우 기사 제외 처리
                    continue

                collection.insert_one({"data": {
                    "headline": text_headline,
                    "content": text_sentence,
                    "company": text_company,
                    "image": image_path
                }})

    def start(self):
        # MultiThread 크롤링 시작
        for category_name in self.selected_category:
            proc = Process(target=self.crawling, args=(category_name,))
            proc.start()


if __name__ == "__main__":
    Crawler = ArticleCrawler()
    Crawler.set_category("정치")
    Crawler.set_date_range(2018, 2018, 1)
    Crawler.start()
