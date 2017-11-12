import os

import pandas as pd
import scrapy
from kafka import KafkaProducer
from scrapy import Request
from scrapy import Selector
from scrapy import signals

from fooltrader.api.hq import get_security_list, kdata_exist, merge_kdata_to_one, remove_quarter_kdata
from fooltrader.consts import DEFAULT_KDATA_HEADER
from fooltrader.contract import data_contract
from fooltrader.contract.files_contract import get_kdata_path_csv
from fooltrader.settings import KAFKA_HOST, AUTO_KAFKA
from fooltrader.utils.utils import get_quarters, get_year_quarter


class StockKDataSpider(scrapy.Spider):
    name = "stock_kdata"

    custom_settings = {
        'DOWNLOAD_DELAY': 1,
        'CONCURRENT_REQUESTS_PER_DOMAIN': 8,

        'SPIDER_MIDDLEWARES': {
            'fooltrader.middlewares.FoolErrorMiddleware': 1000,
        }
    }

    if AUTO_KAFKA:
        producer = KafkaProducer(bootstrap_servers=KAFKA_HOST)

    def yield_request(self, item, trading_dates=[]):
        the_quarters = []
        if trading_dates:
            for the_date in trading_dates:
                the_quarters.append(get_year_quarter(the_date))
        else:
            the_quarters = get_quarters(item['listDate'])

        the_quarters = set(the_quarters)

        # get day k data
        for year, quarter in the_quarters:
            for fuquan in ('hfq', 'bfq'):
                data_path = get_kdata_path_csv(item, year, quarter, fuquan)
                data_exist = os.path.isfile(data_path) or kdata_exist(item, year, quarter, fuquan)

                if not data_exist:
                    url = self.get_k_data_url(item['code'], year, quarter, fuquan)
                    yield Request(url=url, headers=DEFAULT_KDATA_HEADER,
                                  meta={'path': data_path, 'item': item, 'fuquan': fuquan},
                                  callback=self.download_day_k_data)

    def start_requests(self):
        # 两种模式:
        # 1)item,trading_dates不指定,用于全量下载数据
        # 2)指定，用于修复
        item = self.settings.get("security_item")
        trading_dates = self.settings.get("trading_dates")
        if item is not None:
            for request in self.yield_request(item, trading_dates):
                yield request
        else:
            for _, item in get_security_list().iterrows():
                for request in self.yield_request(item):
                    yield request

    def download_day_k_data(self, response):
        path = response.meta['path']
        item = response.meta['item']
        fuquan = response.meta['fuquan']
        trs = response.xpath('//*[@id="FundHoldSharesTable"]/tr[position()>1 and position()<=last()]').extract()

        try:
            if fuquan == 'hfq':
                df = pd.DataFrame(
                    columns=data_contract.KDATA_COLUMN_FQ)

            else:
                df = pd.DataFrame(
                    columns=data_contract.KDATA_COLUMN)

            for idx, tr in enumerate(trs):
                tds = Selector(text=tr).xpath('//td//text()').extract()
                tds = [x.strip() for x in tds if x.strip()]
                securityId = item['id']
                timestamp = tds[0]
                open = float(tds[1])
                high = float(tds[2])
                close = float(tds[3])
                low = float(tds[4])
                volume = tds[5]
                turnover = tds[6]
                if fuquan == 'hfq':
                    factor = tds[7]
                    df.loc[idx] = [timestamp, item['code'], low, open, close, high, volume, turnover, securityId,
                                   factor]
                else:
                    df.loc[idx] = [timestamp, item['code'], low, open, close, high, volume, turnover, securityId]
            df.to_csv(path, index=False)
        except Exception as e:
            self.logger.error('error when getting k data url={} error={}'.format(response.url, e))

    @classmethod
    def from_crawler(cls, crawler, *args, **kwargs):
        spider = super(StockKDataSpider, cls).from_crawler(crawler, *args, **kwargs)
        crawler.signals.connect(spider.spider_closed, signal=signals.spider_closed)
        return spider

    def spider_closed(self, spider, reason):
        spider.logger.info('Spider closed: %s,%s\n', spider.name, reason)
        merge_kdata_to_one()
        remove_quarter_kdata()

    def get_k_data_url(self, code, year, quarter, fuquan):
        if fuquan == 'hfq':
            return 'http://vip.stock.finance.sina.com.cn/corp/go.php/vMS_FuQuanMarketHistory/stockid/{}.phtml?year={}&jidu={}'.format(
                code, year, quarter)
        else:
            return 'http://vip.stock.finance.sina.com.cn/corp/go.php/vMS_MarketHistory/stockid/{}.phtml?year={}&jidu={}'.format(
                code, year, quarter)
