"""Check custom + wide exports: PD payoff consistency, empty CoplayerID/Decision, Part totals."""
import csv
import sys

PD = {('A', 'A'): 70, ('A', 'B'): 0, ('B', 'A'): 100, ('B', 'B'): 30}

def check_custom(path):
    errors = []
    empty_coplayer = []
    part_sum_errors = []
    with open(path, newline='', encoding='utf-8') as f:
        r = csv.DictReader(f)
        rows = list(r)
    for i, row in enumerate(rows):
        pid = row.get('PlayerID', row.get('ProlificID', f'row{i+2}'))
        for r in range(1, 31):
            dec = (row.get(f'Round{r}Decision') or '').strip()
            cop = (row.get(f'Round{r}CoplayerDecision') or '').strip()
            ecoins_s = row.get(f'Round{r}Ecoins', '')
            try:
                ecoins = float(ecoins_s) if ecoins_s else None
            except ValueError:
                ecoins = None
            if dec and cop:
                expected = PD.get((dec, cop))
                if expected is not None and ecoins is not None and abs(ecoins - expected) > 0.01:
                    errors.append((pid, r, dec, cop, ecoins, expected))
            if not cop and dec and r <= 30:
                empty_coplayer.append((pid, r))
        for part, start, end in [(1, 1, 10), (2, 11, 20), (3, 21, 30)]:
            key = f'TotalEarningsPart{part}Ecoins'
            reported = row.get(key, '')
            try:
                reported_val = float(reported) if reported else None
            except ValueError:
                reported_val = None
            if reported_val is not None:
                summed = 0
                for r in range(start, end + 1):
                    s = row.get(f'Round{r}Ecoins', '')
                    try:
                        summed += float(s) if s else 0
                    except ValueError:
                        pass
                if abs(summed - reported_val) > 0.01:
                    part_sum_errors.append((pid, part, reported_val, summed))
    return errors, empty_coplayer, part_sum_errors, len(rows)

def main():
    custom_path = r'c:\Users\waben\Downloads\prisoners_dilemma_2026-03-08.csv'
    payoff_errors, empty_cop, part_errors, n_rows = check_custom(custom_path)
    print('=== Custom export (prisoners_dilemma_2026-03-08.csv) ===')
    print(f'Rows: {n_rows}')
    print(f'Payoff vs PD matrix errors: {len(payoff_errors)}')
    if payoff_errors:
        for e in payoff_errors[:15]:
            print(f'  {e}')
        if len(payoff_errors) > 15:
            print(f'  ... and {len(payoff_errors) - 15} more')
    print(f'Rounds with Decision but empty CoplayerID/CoplayerDecision: {len(empty_cop)}')
    if empty_cop:
        for e in empty_cop[:10]:
            print(f'  {e}')
    print(f'Part total vs sum-of-rounds mismatches: {len(part_errors)}')
    if part_errors:
        for e in part_errors[:10]:
            print(f'  {e}')
    if not payoff_errors and not part_errors:
        print('Payoffs and part totals: OK')
    if not empty_cop:
        print('No empty Coplayer fields for rounds with a decision.')

if __name__ == '__main__':
    main()
