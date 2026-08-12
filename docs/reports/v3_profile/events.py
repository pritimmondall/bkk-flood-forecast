import duckdb, json, glob, os, time, pandas as pd
D="/sessions/compassionate-busy-dijkstra/mnt/bkk-flood-forecast/data/Flood_2019-2025"
con=duckdb.connect(); con.execute("SET memory_limit='2GB'; SET temp_directory='/tmp/prof/tmp'; SET threads=4;")
allev=[]
for f in sorted(glob.glob(D+"/*.csv")):
    yr=int(os.path.basename(f)[:4]); t0=time.time()
    rd=f"read_csv('{f}', header=true, nullstr='NULL', sample_size=300000, types={{'flood':'DOUBLE'}})"
    for tier in (5,15,30):
        q=f"""
        WITH b AS (SELECT flood_code s, site_timestamp t, (flood>={tier}) hi FROM {rd} WHERE flood IS NOT NULL),
        r AS (SELECT s,t,hi, lag(hi) OVER (PARTITION BY s ORDER BY t) ph FROM b),
        g AS (SELECT s,t,hi, sum(CASE WHEN hi AND (ph IS NULL OR NOT ph) THEN 1 ELSE 0 END) OVER (PARTITION BY s ORDER BY t) gid FROM r),
        e AS (SELECT s,gid, min(t) st, max(t) en, count(*) n FROM g WHERE hi GROUP BY 1,2)
        SELECT count(*) raw_excursions,
               sum(CASE WHEN n>=2 THEN 1 ELSE 0 END) ge2readings,
               median(date_diff('minute',st,en)+5) med_dur_min,
               max(date_diff('minute',st,en)+5) max_dur_min,
               count(DISTINCT s) stations_affected
        FROM e"""
        row=con.execute(q).fetchdf().iloc[0].to_dict(); row.update(year=yr,tier=tier)
        allev.append(row)
    print(yr, round(time.time()-t0,1), flush=True)
df=pd.DataFrame(allev); df.to_csv('flood_events.csv',index=False)
print(df.pivot(index='year',columns='tier',values='ge2readings'))
print("\nmedian duration (min) of >=2-reading excursions, by tier:")
print(df.pivot(index='year',columns='tier',values='med_dur_min'))
print("\nstations affected:"); print(df.pivot(index='year',columns='tier',values='stations_affected'))
print("\nTOTAL >=2-reading excursions by tier:"); print(df.groupby('tier')['ge2readings'].sum())
