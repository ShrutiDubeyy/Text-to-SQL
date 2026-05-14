import statistics
from datetime import datetime, timedelta


class AnalyticsEngine:
    """
    YOUR OWN analytics engine.
    Does real data science without LLM.
    """

    def analyze(self, results, columns, question):
        """
        Full analysis of query results.
        Returns insights computed by YOUR code.
        """
        if not results or not columns:
            return {}

        analysis = {}

        # Basic stats
        analysis['basic'] = self._basic_stats(results, columns)

        # Trend detection
        analysis['trend'] = self._detect_trend(results, columns)

        # Anomalies
        analysis['anomalies'] = self._detect_anomalies(
            results, columns
        )

        # Growth rate
        analysis['growth'] = self._calculate_growth(
            results, columns
        )

        # Smart insight
        analysis['insight'] = self._generate_insight(
            results, columns, question, analysis
        )

        return analysis

    def _basic_stats(self, results, columns):
        """YOUR statistical calculations"""
        stats = {}

        for i, col in enumerate(columns):
            values = []
            for row in results:
                try:
                    val = float(row[i])
                    values.append(val)
                except (ValueError, TypeError):
                    pass

            if values:
                stats[col] = {
                    'sum':    round(sum(values), 2),
                    'avg':    round(statistics.mean(values), 2),
                    'max':    round(max(values), 2),
                    'min':    round(min(values), 2),
                    'median': round(statistics.median(values), 2),
                    'count':  len(values)
                }

                # Standard deviation if enough data
                if len(values) > 1:
                    stats[col]['std_dev'] = round(
                        statistics.stdev(values), 2
                    )

        return stats

    def _detect_trend(self, results, columns):
        """
        YOUR trend detection algorithm.
        Looks at numeric progression in results.
        """
        if len(results) < 3:
            return {'direction': 'insufficient_data'}

        # Find numeric column
        numeric_col_idx = None
        for i, col in enumerate(columns):
            try:
                float(results[0][i])
                numeric_col_idx = i
                break
            except (ValueError, TypeError):
                pass

        if numeric_col_idx is None:
            return {'direction': 'no_numeric_data'}

        values = []
        for row in results:
            try:
                values.append(float(row[numeric_col_idx]))
            except (ValueError, TypeError):
                pass

        if len(values) < 3:
            return {'direction': 'insufficient_data'}

        # YOUR trend algorithm
        # Compare first half average vs second half average
        mid = len(values) // 2
        first_half_avg  = statistics.mean(values[:mid])
        second_half_avg = statistics.mean(values[mid:])

        if first_half_avg == 0:
            return {'direction': 'stable'}

        change_pct = (
            (second_half_avg - first_half_avg) / first_half_avg
        ) * 100

        if change_pct > 10:
            direction = 'upward'
            emoji = '📈'
        elif change_pct < -10:
            direction = 'downward'
            emoji = '📉'
        else:
            direction = 'stable'
            emoji = '➡️'

        return {
            'direction':  direction,
            'change_pct': round(change_pct, 1),
            'emoji':      emoji,
            'first_avg':  round(first_half_avg, 2),
            'second_avg': round(second_half_avg, 2)
        }

    def _detect_anomalies(self, results, columns):
        """
        YOUR anomaly detection.
        Uses standard deviation to find outliers.
        """
        anomalies = []

        for i, col in enumerate(columns):
            values = []
            for row in results:
                try:
                    values.append(float(row[i]))
                except (ValueError, TypeError):
                    pass

            if len(values) < 4:
                continue

            mean   = statistics.mean(values)
            stdev  = statistics.stdev(values)

            if stdev == 0:
                continue

            # Flag values more than 2 standard deviations from mean
            for j, val in enumerate(values):
                z_score = abs((val - mean) / stdev)
                if z_score > 2:
                    anomalies.append({
                        'column':  col,
                        'value':   val,
                        'row_idx': j,
                        'z_score': round(z_score, 2),
                        'label':   str(results[j][0])
                    })

        return anomalies

    def _calculate_growth(self, results, columns):
        """
        YOUR growth rate calculation.
        Compares first vs last value.
        """
        if len(results) < 2:
            return None

        for i, col in enumerate(columns):
            try:
                first = float(results[0][i])
                last  = float(results[-1][i])

                if first == 0:
                    continue

                growth = ((last - first) / abs(first)) * 100
                return {
                    'column':     col,
                    'first':      first,
                    'last':       last,
                    'growth_pct': round(growth, 1),
                    'grew':       growth > 0
                }
            except (ValueError, TypeError):
                pass

        return None

    def _generate_insight(self, results, columns,
                          question, analysis):
        """
        YOUR OWN insight generator.
        Uses templates + computed stats.
        No LLM needed.
        """
        q = question.lower()
        parts = []

        # Basic count insight
        row_count = len(results)
        if row_count == 1:
            parts.append(f"Found exactly 1 result.")
        elif row_count <= 5:
            parts.append(f"Found {row_count} results.")
        else:
            parts.append(f"Analyzed {row_count} data points.")

        # Numeric insights
        basic = analysis.get('basic', {})
        for col, stats in basic.items():
            if 'revenue' in col or 'total' in col or 'sales' in col:
                parts.append(
                    f"Total {col}: "
                    f"${stats['sum']:,.2f}"
                )
                parts.append(
                    f"Average: ${stats['avg']:,.2f}"
                )
                if row_count > 1:
                    parts.append(
                        f"Highest: ${stats['max']:,.2f}, "
                        f"Lowest: ${stats['min']:,.2f}"
                    )

        # Trend insight
        trend = analysis.get('trend', {})
        direction = trend.get('direction', '')
        if direction == 'upward':
            parts.append(
                f"{trend.get('emoji','')} Growing trend! "
                f"Up {trend.get('change_pct',0)}% "
                f"from first to second half."
            )
        elif direction == 'downward':
            parts.append(
                f"{trend.get('emoji','')} Declining trend. "
                f"Down {abs(trend.get('change_pct',0))}% "
                f"from first to second half."
            )

        # Anomaly insight
        anomalies = analysis.get('anomalies', [])
        if anomalies:
            a = anomalies[0]
            parts.append(
                f"⚠️ Unusual value detected: "
                f"{a['label']} has {a['column']} = "
                f"{a['value']:,.2f} "
                f"(significantly different from average)"
            )

        # Growth insight
        growth = analysis.get('growth')
        if growth:
            direction_word = "grew" if growth['grew'] else "declined"
            parts.append(
                f"Overall {direction_word} by "
                f"{abs(growth['growth_pct'])}% "
                f"from {growth['first']:,.2f} "
                f"to {growth['last']:,.2f}"
            )

        return " ".join(parts) if parts else "Analysis complete."

    def format_value(self, value, column_name):
        """
        YOUR own smart number formatter.
        No LLM needed.
        """
        if value is None:
            return 'N/A'

        col = str(column_name).lower()

        try:
            num = float(value)
            if (
                'revenue' in col or 'price' in col
                or 'total' in col or 'sales' in col
                or 'cost' in col or 'amount' in col
                or 'budget' in col
            ):
                return f"${num:,.2f}"

            if 'percent' in col or 'rate' in col or '%' in col:
                return f"{num:.1f}%"

            if (
                'count' in col or 'quantity' in col
                or 'orders' in col or 'number' in col
            ):
                return f"{int(num):,}"

            if num >= 1_000_000:
                return f"{num/1_000_000:.1f}M"

            if num >= 1_000:
                return f"{num:,.0f}"

            return f"{num:.2f}"

        except (ValueError, TypeError):
            return str(value)