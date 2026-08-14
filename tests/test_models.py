"""估值模型的單元測試（CLAUDE.md §10：用手算過的固定輸入驗證輸出）。"""
from __future__ import annotations

import datetime as dt

import pytest

from src import config
from src.models import cyclical, m1_pe, m2_pb, river
from src.util import parse_number, percentile, percentile_rank


class FakeRatioPoint:
    def __init__(self, date, per, pbr):
        self.date = date
        self.per = per
        self.pbr = pbr
        self.dividend_yield = None


def build_series():
    """300 個交易日，本益比為 10/20/30/40/50 各 60 天。

    手算分位（線性內插，n=300，position = 299 * q）：
      P10 → 29.9  → 索引 29、30 皆為 10 → 10
      P25 → 74.75 → 索引 74、75 皆為 20 → 20
      P50 → 149.5 → 索引 149、150 皆為 30 → 30
      P75 → 224.25→ 索引 224、225 皆為 40 → 40
      P90 → 269.1 → 索引 269、270 皆為 50 → 50
    """
    today = config.today()
    points = []
    for index in range(300):
        value = [10.0, 20.0, 30.0, 40.0, 50.0][index // 60]
        points.append(FakeRatioPoint(today - dt.timedelta(days=299 - index), value, value))
    return points


class TestPercentile:
    def test_hand_computed(self):
        values = [1.0, 2.0, 3.0, 4.0, 5.0]
        assert percentile(values, 50) == 3.0
        assert percentile(values, 25) == 2.0
        assert percentile(values, 75) == 4.0
        assert percentile(values, 10) == pytest.approx(1.4)
        assert percentile(values, 90) == pytest.approx(4.6)

    def test_single_value(self):
        assert percentile([7.0], 50) == 7.0

    def test_rank_is_share_at_or_below(self):
        values = [10.0] * 60 + [20.0] * 60 + [30.0] * 60 + [40.0] * 60 + [50.0] * 60
        assert percentile_rank(values, 30.0) == pytest.approx(60.0)
        assert percentile_rank(values, 10.0) == pytest.approx(20.0)
        assert percentile_rank(values, 50.0) == pytest.approx(100.0)

    def test_empty_raises(self):
        with pytest.raises(ValueError):
            percentile([], 50)


class TestParseNumber:
    def test_strips_thousands_separator(self):
        assert parse_number("2,390.00") == 2390.0

    def test_missing_tokens_become_none_not_zero(self):
        # 鐵則 7：資料缺漏不得以 0 靜默填補
        for token in ("", "--", "-", "N/A", "－"):
            assert parse_number(token) is None

    def test_real_zero_survives(self):
        assert parse_number("0.00") == 0.0

    def test_signed(self):
        assert parse_number("+85.00") == 85.0
        assert parse_number("-55.00") == -55.0


class TestRocDate:
    def test_three_formats_from_live_endpoints(self):
        expected = dt.date(2026, 8, 13)
        assert config.roc_to_date("1150813") == expected          # STOCK_DAY_ALL
        assert config.roc_to_date("115/08/13") == expected        # STOCK_DAY 個股歷史
        assert config.roc_to_date("115年08月13日") == expected     # BWIBBU 個股歷史

    def test_garbage_returns_none(self):
        assert config.roc_to_date("") is None
        assert config.roc_to_date("--") is None
        assert config.roc_to_date("1159999") is None


class TestM1:
    def test_bands_from_hand_computed_percentiles(self):
        # 現價 600、現值本益比 30 → 推算 TTM EPS = 20
        # low  = P25(20) × 20 = 400
        # mid  = P50(30) × 20 = 600
        # high = P75(40) × 20 = 800
        result = m1_pe.evaluate("2330", "24", build_series(), current_per=30.0, current_price=600.0)
        assert result.applicable
        assert result.low == pytest.approx(400.0)
        assert result.mid == pytest.approx(600.0)
        assert result.high == pytest.approx(800.0)
        assert result.detail["per_share_value"] == pytest.approx(20.0)
        assert result.detail["current_percentile"] == pytest.approx(60.0)
        assert result.detail["samples"] == 300

    def test_negative_eps_is_not_applicable(self):
        # 證交所對虧損股的 PEratio 是空字串 → parse_number 給 None
        result = m1_pe.evaluate("1101", "01", build_series(), current_per=None, current_price=40.0)
        assert not result.applicable
        assert "資料缺漏" in result.reason

    def test_too_few_samples_is_not_applicable(self):
        result = m1_pe.evaluate("2330", "24", build_series()[:100],
                                current_per=30.0, current_price=600.0)
        assert not result.applicable
        assert "有效樣本" in result.reason

    def test_cyclical_warning_by_ticker(self):
        result = m1_pe.evaluate("2327", "28", build_series(), current_per=30.0, current_price=600.0)
        assert any("被動元件" in w for w in result.warnings)
        assert any("反向訊號" in w for w in result.warnings)

    def test_cyclical_warning_by_industry_code(self):
        result = m1_pe.evaluate("2603", "15", build_series(), current_per=30.0, current_price=600.0)
        assert any("航運" in w for w in result.warnings)

    def test_non_cyclical_has_no_warning(self):
        result = m1_pe.evaluate("2330", "24", build_series(), current_per=30.0, current_price=600.0)
        assert result.warnings == []


class TestM2:
    def test_bands_and_mandatory_caveat(self):
        result = m2_pb.evaluate("2330", build_series(), current_pbr=30.0, current_price=600.0)
        assert result.applicable
        assert result.mid == pytest.approx(600.0)
        # 一次性沖銷未自動偵測，必須明說而不是假裝檢查過
        assert any("一次性" in w for w in result.warnings)

    def test_tpex_history_gap_is_surfaced(self):
        result = m2_pb.evaluate("6488", [], current_pbr=3.0, current_price=800.0,
                                unavailable_reason="上櫃個股歷史本益比端點（peQry）已失效")
        assert not result.applicable
        assert "peQry" in result.reason


class TestCyclical:
    def test_named_list_beats_industry_code(self):
        assert cyclical.classify("2409", "26") == "面板"
        assert cyclical.classify("2344", "24") == "記憶體"

    def test_industry_codes(self):
        assert cyclical.classify("1301", "03") == "塑膠"
        assert cyclical.classify("2002", "10") == "鋼鐵"
        assert cyclical.classify("1717", "21") == "化學工業"

    def test_semiconductor_is_not_cyclical_by_default(self):
        assert cyclical.classify("2330", "24") is None


class TestRiverGuards:
    def test_zero_price_rejected(self):
        result = river.build("M1", "P/E 河流圖", [(p.date, p.per) for p in build_series()],
                             current_ratio=30.0, current_price=0.0, per_share_label="TTM EPS")
        assert not result.applicable


class TestRatioLabel:
    def test_body_text_uses_ratio_name_not_chart_title(self):
        # 「目前 P/E 河流圖 32.74」讀不通；內文要說「本益比」
        result = m1_pe.evaluate("2330", "24", build_series(), current_per=30.0, current_price=600.0)
        assert result.title == "P/E 河流圖"
        assert result.detail["ratio_label"] == "本益比"

        m2 = m2_pb.evaluate("2330", build_series(), current_pbr=30.0, current_price=600.0)
        assert m2.detail["ratio_label"] == "股價淨值比"

    def test_unavailable_reason_uses_ratio_name(self):
        result = m1_pe.evaluate("1101", "01", build_series(), current_per=None, current_price=40.0)
        assert "目前本益比" in result.reason
