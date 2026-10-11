"""Offline margin math and rendering regressions."""

import sys
import unittest
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "my-dash-app"))
from components.sales_trend import aggregate_sales_trend, sales_trend_figure


class SalesTrendTests(unittest.TestCase):
    def frame(self):
        return pd.DataFrame(
            {
                "order_date": pd.to_datetime(
                    ["2026-01-01", "2026-01-01", "2026-01-03"]
                ),
                "gross_sales_amount": [100.0, 900.0, 100.0],
                "quantity": [2, 3, 1],
                "cost": [40.0, 100.0, 150.0],
            }
        )

    def test_weighted_margin_quantity_and_loss(self):
        frame = self.frame()
        original = frame.copy(deep=True)
        trend = aggregate_sales_trend(frame, "D")
        self.assertEqual(list(trend.revenue), [1000, 0, 100])
        self.assertAlmostEqual(trend.margin.iloc[0], 0.62)
        self.assertTrue(pd.isna(trend.margin.iloc[1]))
        self.assertEqual(trend.margin.iloc[2], -0.5)
        pd.testing.assert_frame_equal(frame, original)
        monthly = aggregate_sales_trend(frame, "ME")
        self.assertAlmostEqual(monthly.margin.iloc[0], (1100 - 530) / 1100)

    def test_missing_invalid_cost_or_quantity_never_invents_margin(self):
        for column, value in [
            ("cost", None),
            ("cost", -5),
            ("cost", "bad"),
            ("quantity", None),
            ("cost", float("inf")),
        ]:
            frame = self.frame()
            frame[column] = frame[column].astype(object)
            frame.loc[0, column] = value
            trend = aggregate_sales_trend(frame, "D")
            self.assertTrue(pd.isna(trend.margin.iloc[0]))
            self.assertEqual(trend.revenue.iloc[0], 1000)
        frame = self.frame().drop(columns="cost")
        figure = sales_trend_figure(frame, "D")
        self.assertIn("Margin unavailable", figure.layout.annotations[0].text)
        self.assertTrue(all(pd.isna(value) for value in figure.data[1].y))

    def test_distinct_traces_axes_and_unclipped_negative_margin(self):
        figure = sales_trend_figure(self.frame(), "D")
        self.assertEqual([trace.type for trace in figure.data], ["bar", "scatter"])
        self.assertEqual(figure.data[1].yaxis, "y2")
        self.assertFalse(figure.data[1].connectgaps)
        self.assertEqual(figure.layout.yaxis2.tickformat, ".0%")
        self.assertLess(figure.layout.yaxis2.range[0], -0.5)
