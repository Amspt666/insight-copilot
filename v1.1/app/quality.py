"""Read-only accounting invariants for the selected company/currency scope."""


def ledger_checks(con, params: dict) -> dict:
    company_params = sorted(key for key in params if key.startswith('company'))
    companies = ','.join(':' + key for key in company_params)
    scope = f"h.MANDT='800' AND h.BUKRS IN ({companies}) AND h.WAERS=:currency"
    # The simulated ledger is deliberately double-entry. Check both units.
    unbalanced = con.execute(f'''
        SELECT COUNT(*) FROM (
          SELECT h.MANDT,h.BUKRS,h.GJAHR,h.BELNR
          FROM BKPF h JOIN BSEG b ON h.MANDT=b.MANDT AND h.BUKRS=b.BUKRS AND h.GJAHR=b.GJAHR AND h.BELNR=b.BELNR
          WHERE {scope}
          GROUP BY h.MANDT,h.BUKRS,h.GJAHR,h.BELNR
          HAVING SUM(CASE WHEN b.SHKZG='S' THEN b.WRBTR ELSE -b.WRBTR END)<>0
          OR SUM(CASE WHEN b.SHKZG='S' THEN b.DMBTR ELSE -b.DMBTR END)<>0
          OR SUM(CASE WHEN typeof(b.WRBTR)<>'integer' OR typeof(b.DMBTR)<>'integer' THEN 1 ELSE 0 END)>0
        )''', params).fetchone()[0]
    # Every DZ/DG customer credit is completely allocated in this version.
    missing_allocations = con.execute(f'''
        SELECT COUNT(*) FROM (
          SELECT h.MANDT,h.BUKRS,h.GJAHR,h.BELNR,b.BUZEI,b.WRBTR
          FROM BKPF h JOIN BSEG b ON h.MANDT=b.MANDT AND h.BUKRS=b.BUKRS AND h.GJAHR=b.GJAHR AND h.BELNR=b.BELNR
          LEFT JOIN ZAR_APPLICATION a ON a.MANDT=b.MANDT AND a.BUKRS=b.BUKRS
            AND a.PAY_GJAHR=b.GJAHR AND a.PAY_BELNR=b.BELNR AND a.PAY_BUZEI=b.BUZEI
          WHERE {scope} AND h.BLART IN ('DZ','DG') AND b.KOART='D'
          GROUP BY h.MANDT,h.BUKRS,h.GJAHR,h.BELNR,b.BUZEI,b.WRBTR
          HAVING COALESCE(SUM(a.AMOUNT),0)<>b.WRBTR
        )''', params).fetchone()[0]
    invalid_links = con.execute(f'''
        SELECT COUNT(*) FROM ZAR_APPLICATION a
        LEFT JOIN BSEG i ON a.MANDT=i.MANDT AND a.BUKRS=i.BUKRS AND a.INV_GJAHR=i.GJAHR AND a.INV_BELNR=i.BELNR AND a.INV_BUZEI=i.BUZEI
        LEFT JOIN BKPF h ON i.MANDT=h.MANDT AND i.BUKRS=h.BUKRS AND i.GJAHR=h.GJAHR AND i.BELNR=h.BELNR
        LEFT JOIN BSEG p ON a.MANDT=p.MANDT AND a.BUKRS=p.BUKRS AND a.PAY_GJAHR=p.GJAHR AND a.PAY_BELNR=p.BELNR AND a.PAY_BUZEI=p.BUZEI
        LEFT JOIN BKPF ph ON p.MANDT=ph.MANDT AND p.BUKRS=ph.BUKRS AND p.GJAHR=ph.GJAHR AND p.BELNR=ph.BELNR
        WHERE a.MANDT='800' AND a.BUKRS IN ({companies}) AND (h.WAERS=:currency OR h.WAERS IS NULL)
          AND (i.BELNR IS NULL OR p.BELNR IS NULL OR ph.BELNR IS NULL OR h.BELNR IS NULL
          OR i.KUNNR<>p.KUNNR OR h.WAERS<>ph.WAERS OR i.KOART<>'D' OR p.KOART<>'D'
          OR h.BLART<>'DR' OR ph.BLART NOT IN ('DZ','DG') OR i.SHKZG<>'S' OR p.SHKZG<>'H'
          OR a.APPLIED_ON<h.BUDAT OR a.APPLIED_ON<ph.BUDAT OR a.AMOUNT<=0 OR typeof(a.AMOUNT)<>'integer')
        ''', params).fetchone()[0]
    return {'unbalanced_documents': unbalanced, 'unallocated_credit_documents': missing_allocations,
            'invalid_application_links': invalid_links}
