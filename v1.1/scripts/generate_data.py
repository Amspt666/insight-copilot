"""Generate a small, reproducible ledger. No network or LLM required.

This is data construction, not a test runner. Monetary values are integer cents.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import date, timedelta
import json
from pathlib import Path
import random
import sqlite3

ROOT = Path(__file__).resolve().parents[1]
START, END = date(2025, 1, 1), date(2026, 6, 30)
SCHEMA = '''
PRAGMA foreign_keys=ON;
CREATE TABLE T001(MANDT TEXT, BUKRS TEXT, BUTXT TEXT, WAERS TEXT, PRIMARY KEY(MANDT,BUKRS));
CREATE TABLE KNA1(MANDT TEXT, KUNNR TEXT, NAME1 TEXT, SORTL TEXT, PRIMARY KEY(MANDT,KUNNR));
CREATE TABLE KNB1(MANDT TEXT, KUNNR TEXT, BUKRS TEXT, ZTERM TEXT,
 PRIMARY KEY(MANDT,KUNNR,BUKRS), FOREIGN KEY(MANDT,KUNNR) REFERENCES KNA1,
 FOREIGN KEY(MANDT,BUKRS) REFERENCES T001);
CREATE TABLE BKPF(MANDT TEXT, BUKRS TEXT, GJAHR TEXT, BELNR TEXT, BLART TEXT,
 BUDAT TEXT, BLDAT TEXT, WAERS TEXT, PRIMARY KEY(MANDT,BUKRS,GJAHR,BELNR),
 FOREIGN KEY(MANDT,BUKRS) REFERENCES T001);
CREATE TABLE BSEG(MANDT TEXT, BUKRS TEXT, GJAHR TEXT, BELNR TEXT, BUZEI TEXT,
 KOART TEXT CHECK(KOART IN ('D','S')), KUNNR TEXT, SHKZG TEXT CHECK(SHKZG IN ('S','H')),
 WRBTR INTEGER CHECK(WRBTR>=0), DMBTR INTEGER CHECK(DMBTR>=0), ZFBDT TEXT, ZBD1T INTEGER,
 AUGBL TEXT, AUGDT TEXT, PRIMARY KEY(MANDT,BUKRS,GJAHR,BELNR,BUZEI),
 FOREIGN KEY(MANDT,BUKRS,GJAHR,BELNR) REFERENCES BKPF);
CREATE TABLE ZAR_APPLICATION(ID INTEGER PRIMARY KEY, MANDT TEXT, BUKRS TEXT,
 INV_GJAHR TEXT, INV_BELNR TEXT, INV_BUZEI TEXT,
 PAY_GJAHR TEXT, PAY_BELNR TEXT, PAY_BUZEI TEXT, APPLIED_ON TEXT, AMOUNT INTEGER CHECK(AMOUNT>0),
 FOREIGN KEY(MANDT,BUKRS,INV_GJAHR,INV_BELNR,INV_BUZEI) REFERENCES BSEG,
 FOREIGN KEY(MANDT,BUKRS,PAY_GJAHR,PAY_BELNR,PAY_BUZEI) REFERENCES BSEG);
CREATE TABLE ZDEMO_META(KEY TEXT PRIMARY KEY, VALUE TEXT);
CREATE INDEX ix_bkpf_date ON BKPF(BUKRS,WAERS,BUDAT,BLART);
CREATE INDEX ix_bseg_customer ON BSEG(KUNNR,BUKRS,KOART);
CREATE INDEX ix_application_invoice ON ZAR_APPLICATION(MANDT,BUKRS,INV_GJAHR,INV_BELNR,INV_BUZEI,APPLIED_ON);
'''


class Ledger:
    def __init__(self, con):
        self.con = con
        self.sequence = defaultdict(int)
        self.invoices = []
        self.receipts = []

    def document(self, company, customer, day, amount, kind, currency='CNY', term=30):
        year = str(day.year)
        self.sequence[company, year] += 1
        number = str(self.sequence[company, year]).zfill(10)
        key = ('800', company, year, number)
        self.con.execute('INSERT INTO BKPF VALUES (?,?,?,?,?,?,?,?)',
                         (*key, kind, day.isoformat(), day.isoformat(), currency))
        base = amount * (7 if currency == 'USD' else 1)
        debit = kind == 'DR'
        for item, account, cust, sign in (
            ('001', 'D', customer, 'S' if debit else 'H'),
            ('002', 'S', None, 'H' if debit else 'S'),
        ):
            self.con.execute('INSERT INTO BSEG VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                             (*key, item, account, cust, sign, amount, base,
                              day.isoformat(), term, None, None))
        if kind == 'DZ':
            self.receipts.append(dict(company=company, customer=customer, date=day.isoformat(), currency=currency, cents=amount))
        return key

    def invoice(self, company, customer, day, amount, currency='CNY', term=30):
        inv = dict(key=self.document(company, customer, day, amount, 'DR', currency, term),
                   company=company, customer=customer, date=day.isoformat(),
                   due=(day + timedelta(days=term)).isoformat(), currency=currency,
                   cents=amount, applications=[])
        self.invoices.append(inv)
        return inv

    def apply(self, invoice, day, amount, kind='DZ', payment=None):
        key = invoice['key']
        pay = payment or self.document(invoice['company'], invoice['customer'], day, amount, kind, invoice['currency'])
        self.con.execute('''INSERT INTO ZAR_APPLICATION
          (MANDT,BUKRS,INV_GJAHR,INV_BELNR,INV_BUZEI,PAY_GJAHR,PAY_BELNR,PAY_BUZEI,APPLIED_ON,AMOUNT)
          VALUES (?,?,?,?,?,?,?,?,?,?)''',
          (*key, '001', pay[2], pay[3], '001', day.isoformat(), amount))
        invoice['applications'].append(dict(date=day.isoformat(), cents=amount, kind=kind))
        if sum(x['cents'] for x in invoice['applications']) == invoice['cents']:
            self.con.execute('UPDATE BSEG SET AUGBL=?,AUGDT=? WHERE MANDT=? AND BUKRS=? AND GJAHR=? AND BELNR=? AND BUZEI=?',
                             (pay[3], day.isoformat(), *key, '001'))


def controls(ledger):
    """Independent event-side reference totals; does not call the query compiler."""
    result = []
    for as_of in ('2025-12-31', '2026-01-31', '2026-05-31', '2026-06-30'):
        for company in ('1000', '2000'):
            for currency in ('CNY', 'USD'):
                balance = overdue = 0
                for inv in ledger.invoices:
                    if inv['company'] != company or inv['currency'] != currency or inv['date'] > as_of:
                        continue
                    remaining = inv['cents'] - sum(x['cents'] for x in inv['applications'] if x['date'] <= as_of)
                    balance += remaining
                    if inv['due'] < as_of:
                        overdue += remaining
                receipts = sum(x['cents'] for x in ledger.receipts if x['company'] == company and x['currency'] == currency and as_of[:7] + '-01' <= x['date'] <= as_of)
                result.append(dict(as_of=as_of, company=company, currency=currency,
                                   ar_balance_cents=balance, overdue_ar_cents=overdue, month_receipts_cents=receipts))
    return result


def generate(seed=20260923, invoice_count=1100, force=False):
    target = ROOT / 'data' / 'finance.sqlite'
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and not force:
        raise SystemExit('数据库已存在。需重建时请关闭服务并显式使用 --force。')
    temp = target.with_suffix('.tmp')
    if temp.exists():
        raise SystemExit('存在上次生成的 finance.tmp，请检查后手工删除再运行。')
    rng = random.Random(seed)
    con = sqlite3.connect(temp)
    try:
        con.executescript(SCHEMA)
        con.executemany('INSERT INTO T001 VALUES (?,?,?,?)', [('800','1000','华东贸易有限公司','CNY'), ('800','2000','华南贸易有限公司','CNY')])
        prefixes = ['远山', '澄海', '松柏', '星河', '青禾', '锦川', '云帆', '博源', '启明', '嘉木']
        sectors = ['设备', '商贸', '材料', '科技', '物流']
        for index in range(50):
            customer = str(index + 1).zfill(10)
            alias = prefixes[index % 10] + sectors[index // 10]
            con.execute('INSERT INTO KNA1 VALUES (?,?,?,?)', ('800', customer, alias + '有限公司', alias))
            for company in ('1000', '2000'):
                con.execute('INSERT INTO KNB1 VALUES (?,?,?,?)', ('800', customer, company, 'N030'))
        ledger = Ledger(con)
        # Dedicated customer 0000000001 is excluded from random generation.
        fixture = ledger.invoice('1000', '0000000001', date(2025,12,15), 1000000, term=30)
        ledger.apply(fixture, date(2026,1,10), 400000)
        ledger.apply(fixture, date(2026,2,10), 100000, 'DG')
        ledger.apply(fixture, date(2026,3,10), 500000)
        # One receipt allocated to two invoices, with matching company/customer/currency.
        a = ledger.invoice('2000', '0000000001', date(2026,5,1), 300000)
        b = ledger.invoice('2000', '0000000001', date(2026,5,15), 200000)
        pay = ledger.document('2000', '0000000001', date(2026,6,5), 400000, 'DZ')
        ledger.apply(a, date(2026,6,5), 300000, payment=pay)
        ledger.apply(b, date(2026,6,5), 100000, payment=pay)
        for _ in range(invoice_count):
            day = START + timedelta(days=rng.randrange((END-START).days + 1))
            company = rng.choice(('1000','2000'))
            customer = str(rng.randint(2,50)).zfill(10)
            currency = 'USD' if rng.random() < 0.12 else 'CNY'
            amount = rng.randint(10000, 2000000)
            inv = ledger.invoice(company, customer, day, amount, currency, rng.choice((15,30,45,60)))
            if rng.random() < 0.2:
                continue
            first = day + timedelta(days=rng.randint(5,85))
            partial = amount * rng.choice((40,60,100)) // 100
            if first <= END:
                ledger.apply(inv, first, partial)
                remain = amount-partial
                second = first + timedelta(days=rng.randint(10,90))
                if remain and second <= END and rng.random() < 0.75:
                    if rng.random() < 0.2:
                        credit = remain // 5
                        ledger.apply(inv, second, credit, 'DG')
                        remain -= credit
                    ledger.apply(inv, second, remain)
        meta = dict(seed=seed, start=START.isoformat(), end=END.isoformat(), today='2026-07-01',
                    version='1.1.0', money_unit='integer cents', simulated=True)
        con.executemany('INSERT INTO ZDEMO_META VALUES (?,?)', [(k,json.dumps(v,ensure_ascii=False)) for k,v in meta.items()])
        con.commit()
        counts = {table: con.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0] for table in ('T001','KNA1','KNB1','BKPF','BSEG','ZAR_APPLICATION')}
    finally:
        con.close()
    temp.replace(target)
    (ROOT / 'data' / 'manifest.json').write_text(json.dumps({**meta, 'counts': counts},ensure_ascii=False,indent=2),encoding='utf-8')
    (ROOT / 'data' / 'control_totals.json').write_text(json.dumps(controls(ledger),ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'created':str(target),'counts':counts,'tests_run':False},ensure_ascii=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seed', type=int, default=20260923)
    parser.add_argument('--invoices', type=int, default=1100)
    parser.add_argument('--force', action='store_true')
    args = parser.parse_args()
    if not 0 <= args.invoices <= 10000:
        parser.error('--invoices must be between 0 and 10000')
    generate(args.seed, args.invoices, args.force)
