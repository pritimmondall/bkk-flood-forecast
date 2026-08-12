import duckdb, json, glob, os, time
D="/sessions/compassionate-busy-dijkstra/mnt/bkk-flood-forecast/data"
OUT="/tmp/prof"
con=duckdb.connect()
con.execute("SET memory_limit='2GB'; SET temp_directory='/tmp/prof/tmp'; SET threads=4; SET preserve_insertion_order=false;")
SETS={
 "flood":(f"{D}/Flood_2019-2025","flood_code","flood_name",["flood"]),
 "flow": (f"{D}/Flow_2019-2025","flow_code","flow_name",["flow","wl","area","mean_velocity"]),
 "rain": (f"{D}/Rain_2019-2025","rain_code","rain_name",["rf5min","rf15min","rf30min","rf1hr","rf3hr","rf6hr","rf12hr","rf24hr"]),
 "water":(f"{D}/Water_2019-2025","water_code","water_name",["wl_in","wl_out01","wl_out02"]),
}
P=OUT+"/station_profile.json"
res=json.load(open(P)) if os.path.exists(P) else {}
for name,(d,code,nm,vals) in SETS.items():
    res.setdefault(name,{})
    for f in sorted(glob.glob(d+"/*.csv")):
        yr=os.path.basename(f).replace(".csv","").replace("Rain ","").strip()
        if yr in res[name]: continue
        t0=time.time()
        rd=f"read_csv('{f}', header=true, nullstr='NULL', sample_size=300000, types={{{','.join(chr(39)+v+chr(39)+':'+chr(39)+'DOUBLE'+chr(39) for v in vals)}}})"
        aggs=[]
        for v in vals:
            aggs += [f"count({v})::BIGINT AS n_{v}", f"min({v}) AS min_{v}", f"max({v}) AS max_{v}", f"avg({v}) AS avg_{v}"]
        extra=""
        if name=="flood":
            extra=""", sum(CASE WHEN flood>=5 THEN 1 ELSE 0 END)::BIGINT AS n_ge5,
                    sum(CASE WHEN flood>=15 THEN 1 ELSE 0 END)::BIGINT AS n_ge15,
                    sum(CASE WHEN flood>=30 THEN 1 ELSE 0 END)::BIGINT AS n_ge30,
                    sum(CASE WHEN flood>0 THEN 1 ELSE 0 END)::BIGINT AS n_gt0,
                    sum(CASE WHEN flood<0 THEN 1 ELSE 0 END)::BIGINT AS n_neg"""
        q=f"""SELECT {code} AS station, count(*)::BIGINT AS rows,
               min(site_timestamp) AS ts_min, max(site_timestamp) AS ts_max,
               count(DISTINCT site_timestamp)::BIGINT AS n_ts,
               any_value({nm}) AS name, {', '.join(aggs)}{extra}
             FROM {rd} GROUP BY 1 ORDER BY 1"""
        df=con.execute(q).fetchdf()
        res[name][yr]=json.loads(df.to_json(orient='records',date_format='iso'))
        json.dump(res,open(P,"w"))
        print(name,yr,len(df),int(df['rows'].sum()),round(time.time()-t0,1),flush=True)
print("ALLDONE")
