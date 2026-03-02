"""Check prisoners_dilemma_custom_export CSV for nulls and payoff correctness."""
import csv
from pathlib import Path

PD_PAYOFFS = {
    ('A', 'A'): 70,
    ('A', 'B'): 0,
    ('B', 'A'): 100,
    ('B', 'B'): 30,
}

def is_empty(v):
    if v is None: return True
    s = (v or "").strip().lower()
    return s in ('', 'none', 'null', 'nan')

def main():
    path = Path("prisoners_dilemma_custom_export_2026-03-01.csv")
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    if not rows:
        print("No data rows")
        return

    fieldnames = list(rows[0].keys())
    issues = []
    null_counts = {c: 0 for c in fieldnames}
    payoff_errors = []
    part_sum_errors = []

    for i, row in enumerate(rows):
        pid = row.get("ProlificID", f"row{i+2}")
        # Null check
        for col in fieldnames:
            if is_empty(row.get(col)):
                null_counts[col] += 1

        # Payoff check rounds 1-30
        for r in range(1, 31):
            dec = row.get(f"Round{r}Decision", "").strip().upper()
            cop = row.get(f"Round{r}CoplayerDecision", "").strip().upper()
            ecoins = row.get(f"Round{r}Ecoins", "")
            if not dec or not cop:
                continue
            if dec not in ("A", "B") or cop not in ("A", "B"):
                issues.append(f"{pid} Round{r}: invalid decision '{dec}' or '{cop}'")
                continue
            try:
                actual = float(ecoins) if ecoins else None
            except (ValueError, TypeError):
                issues.append(f"{pid} Round{r}: non-numeric Ecoins '{ecoins}'")
                continue
            expected = PD_PAYOFFS.get((dec, cop))
            if expected is not None and actual is not None and actual != expected:
                payoff_errors.append(f"{pid} Round{r}: choice ({dec},{cop}) => expected {expected}, got {actual}")

        # Part totals = sum of round ecoins
        for part, (start, end) in [(1, (1, 11)), (2, (11, 21)), (3, (21, 31))]:
            part_sum = 0
            for r in range(start, end):
                v = row.get(f"Round{r}Ecoins", "")
                try:
                    part_sum += float(v) if v else 0
                except ValueError:
                    pass
            total_col = f"TotalEarningsPart{part}Ecoins"
            reported = row.get(total_col, "")
            try:
                reported_f = float(reported) if reported else None
            except ValueError:
                reported_f = None
            if reported_f is not None and abs(part_sum - reported_f) > 0.01:
                part_sum_errors.append(f"{pid} {total_col}: sum rounds {start}-{end-1} = {part_sum}, reported {reported_f}")

    # Report
    print("=== NULL / EMPTY COUNTS (columns with at least one empty) ===")
    for col in sorted(null_counts.keys()):
        n = null_counts[col]
        if n > 0:
            print(f"  {col}: {n}/{len(rows)} empty")

    print("\n=== PAYOFF ERRORS (RoundXEcoins vs PD matrix) ===")
    if not payoff_errors:
        print("  None found. All round payoffs match (A,A)=70, (A,B)=0, (B,A)=100, (B,B)=30.")
    else:
        for e in payoff_errors[:30]:
            print(f"  {e}")
        if len(payoff_errors) > 30:
            print(f"  ... and {len(payoff_errors) - 30} more")

    print("\n=== PART TOTAL ERRORS (sum of round ecoins vs TotalEarningsPart*Ecoins) ===")
    if not part_sum_errors:
        print("  None found.")
    else:
        for e in part_sum_errors[:20]:
            print(f"  {e}")
        if len(part_sum_errors) > 20:
            print(f"  ... and {len(part_sum_errors) - 20} more")

    print("\n=== OTHER ISSUES ===")
    if not issues:
        print("  None.")
    else:
        for e in issues[:15]:
            print(f"  {e}")
        if len(issues) > 15:
            print(f"  ... and {len(issues) - 15} more")

    # Part 4 guess earnings: 0 or 10.0
    print("\n=== PART 4 GUESS EARNINGS (sample) ===")
    for col in ["EarningsGuess1", "EarningsGuess5", "EarningsGuess10"]:
        vals = [row.get(col, "") for row in rows[:5]]
        print(f"  {col}: {vals}")

if __name__ == "__main__":
    main()
