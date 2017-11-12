from pytdx.hq import TdxHq_API

from fooltrader.api import hq
from fooltrader.contract.data_contract import KDATA_COLUMN
from fooltrader.utils.utils import get_exchange


def get_tdx_kdata(security_item, start, end):
    api = TdxHq_API()
    with api.connect():
        # open close high low vol amount date code
        # KDATA_COLUMN = ['timestamp', 'code', 'low', 'open', 'close', 'high', 'volume', 'turnover', 'securityId']

        df = api.get_k_data(security_item['code'], start, end)
        df = df[['date', 'code', 'low', 'open', 'close', 'high', 'vol', 'amount']]
        df['securityId'] = df['code'].apply(lambda x: 'stock_{}_{}'.format(get_exchange(x), x))
        df['vol'] = df['vol'].apply(lambda x: x * 100)
        df.columns = KDATA_COLUMN
    return df


def save_tdx_kdata(security_item, start, end):
    df = get_tdx_kdata(security_item, start, end)
    hq.merge_to_current_kdata(security_item, df)


if __name__ == '__main__':
    pass
