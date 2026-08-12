import json, pandas as pd
res=json.load(open('station_profile.json'))
out={}
for ds,years in res.items():
    rows=[]
    for yr,recs in years.items():
        df=pd.DataFrame(recs); df['year']=int(yr); df['dataset']=ds; rows.append(df)
    out[ds]=pd.concat(rows,ignore_index=True)
    out[ds].to_csv(f'{ds}_stations.csv',index=False)
print("=== station counts by year")
tab={ds:d.groupby('year')['station'].nunique() for ds,d in out.items()}
print(pd.DataFrame(tab))
print("\n=== rows by year (millions)")
print(pd.DataFrame({ds:(d.groupby('year')['rows'].sum()/1e6).round(2) for ds,d in out.items()}))
print("\n=== duplicate timestamps (rows - n_ts) by dataset-year")
print(pd.DataFrame({ds:(d.groupby('year').apply(lambda g:(g['rows']-g['n_ts']).sum())) for ds,d in out.items()}))
print("\n=== stations appearing in only some years")
for ds,d in out.items():
    c=d.groupby('station')['year'].nunique()
    print(ds,'total',len(c),'| in all 7:',int((c==7).sum()),'| partial:',int((c<7).sum()))
    if (c<7).sum(): print('   ',dict(c[c<7]))
fl=out['flood']
print("\n=== FLOOD target")
print('total rows', int(fl['rows'].sum()))
for k in ['n_gt0','n_ge5','n_ge15','n_ge30','n_neg']:
    print(f'  {k}: {int(fl[k].sum()):,}  ({fl[k].sum()/fl["rows"].sum()*100:.4f}%)  1 in {fl["rows"].sum()/max(fl[k].sum(),1):,.0f}')
print('  n_flood non-null', int(fl['n_flood'].sum()), 'null%', round(100*(1-fl['n_flood'].sum()/fl['rows'].sum()),4))
print('  max depth observed', fl['max_flood'].max(), 'min', fl['min_flood'].min())
print("\n--- per year positive rate at 15cm")
g=fl.groupby('year')[['rows','n_ge5','n_ge15','n_ge30']].sum()
g['pct_ge15']=(g['n_ge15']/g['rows']*100).round(4); g['pct_ge5']=(g['n_ge5']/g['rows']*100).round(4)
print(g)
print("\n--- top 15 stations by n_ge15 (all years)")
t=fl.groupby(['station'])[['n_ge15','n_ge5','n_ge30']].sum().sort_values('n_ge15',ascending=False).head(15)
print(t)
print("\n--- flood stations with ZERO readings >=15cm ever:", int((fl.groupby('station')['n_ge15'].sum()==0).sum()), 'of', fl['station'].nunique())
print("--- flood stations with ZERO readings >=5cm ever:", int((fl.groupby('station')['n_ge5'].sum()==0).sum()))
print("\n=== RAIN ranges")
r=out['rain']
print(r[['max_rf5min','max_rf1hr','max_rf24hr']].max())
print('null% rf1hr', round(100*(1-r['n_rf1hr'].sum()/r['rows'].sum()),3))
print("\n=== WATER ranges / nulls")
w=out['water']
print('wl_in null%', round(100*(1-w['n_wl_in'].sum()/w['rows'].sum()),2),
      '| wl_out01 null%', round(100*(1-w['n_wl_out01'].sum()/w['rows'].sum()),2),
      '| wl_out02 null%', round(100*(1-w['n_wl_out02'].sum()/w['rows'].sum()),2))
print('wl_in min/max', w['min_wl_in'].min(), w['max_wl_in'].max())
print("\n=== FLOW ranges")
fw=out['flow']
print('flow min/max', fw['min_flow'].min(), fw['max_flow'].max())
print(fw.groupby('station')[['min_flow','max_flow']].agg({'min_flow':'min','max_flow':'max'}).sort_values('max_flow',ascending=False).head(6))
print('null% flow', round(100*(1-fw['n_flow'].sum()/fw['rows'].sum()),2), 'area', round(100*(1-fw['n_area'].sum()/fw['rows'].sum()),2))
# prefix coverage
import re
pref=lambda s: s.split('.')[1] if len(s.split('.'))>1 else None
fp=set(map(pref,fl['station'].unique())); rp=set(map(pref,r['station'].unique()))
wp=set(map(pref,w['station'].unique())); wfp=set(map(pref,fw['station'].unique()))
print("\n=== code-prefix coverage of the %d flood prefixes"%len(fp))
print('rain covers', len(fp&rp), '| water covers', len(fp&wp), '| flow covers', len(fp&wfp))
print('flood prefixes with no rain prefix:', sorted(fp-rp))
