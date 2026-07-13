from stockoftheday.universe import parse_symbol_directory

NASDAQ_SAMPLE = """Symbol|Security Name|Market Category|Test Issue|Financial Status|Round Lot Size|ETF|NextShares
LMFA|LM Funding America, Inc. - Common Stock|S|N|D|100|N|N
AAAP|Pacer Barings CLO Market Flex ETF|G|N|N|100|Y|N
ZTEST|NASDAQ TEST STOCK|G|Y|N|100|N|N
ABCDW|Some Company - Warrant|S|N|N|100|N|N
GOODW|Goodwill Industries - Common Stock|S|N|N|100|N|N
File Creation Time: 0713202520:30|||||||
"""

OTHER_SAMPLE = """ACT Symbol|Security Name|Exchange|CQS Symbol|ETF|Round Lot Size|Test Issue|NASDAQ Symbol
GE|GE Aerospace Common Stock|N|GE|N|100|N|GE
SPY|SPDR S&P 500 ETF Trust|P|SPY|Y|100|N|SPY
BRK.A|Berkshire Hathaway Inc. Class A|N|BRK A|N|1|N|BRK.A
ABC$D|Some Corp Preferred Series D|N|ABC pD|N|100|N|ABC-D
XYZ|XYZ Corp 7.5% Notes due 2045|N|XYZ|N|100|N|XYZ
PENY|Tiny Penny Corp Common Stock|A|PENY|N|100|N|PENY
File Creation Time: 0713202520:30|||||||
"""


def test_parser_keeps_common_stock_including_pennies():
    syms = parse_symbol_directory(NASDAQ_SAMPLE, OTHER_SAMPLE)
    assert "LMFA" in syms
    assert "GE" in syms
    assert "PENY" in syms  # NYSE American penny stock


def test_parser_drops_etfs_test_issues_and_non_common():
    syms = parse_symbol_directory(NASDAQ_SAMPLE, OTHER_SAMPLE)
    assert "AAAP" not in syms    # ETF flag
    assert "SPY" not in syms     # ETF flag
    assert "ZTEST" not in syms   # test issue
    assert "ABCDW" not in syms   # warrant by name
    assert "BRK.A" not in syms   # dotted class share
    assert "ABC$D" not in syms   # preferred
    assert "XYZ" not in syms     # notes by name


def test_parser_name_filter_is_not_overeager():
    # "GOODW" ends in W but the name says common stock — must survive
    syms = parse_symbol_directory(NASDAQ_SAMPLE, OTHER_SAMPLE)
    assert "GOODW" in syms


def test_parser_output_sorted_unique():
    syms = parse_symbol_directory(NASDAQ_SAMPLE, OTHER_SAMPLE)
    assert syms == sorted(set(syms))
