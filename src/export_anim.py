"""
產生 agent 移動動畫（§11）。左右並排兩張 Leaflet 地圖：左=未取得資訊、右=取得資訊，
同一批缺車 agent、同一時鐘，動畫呈現每個 agent 走路(灰)/騎車(綠)如何移動到目的地。
輸出 results/anim.html（自含資料，瀏覽器直接開）。

agent 路徑（與模擬一致，依抵達時間先到先服務配置調度容量）：
  無資訊：走到最近站 m → m 恰為調度站且有餘量則騎去 dst，否則再走去 dst
  有資訊：走到容忍距離內最近且有餘量的調度站 g 騎去 dst，否則走去 dst
（動畫不畫還車段，標題註明 cost 另含還車側。）
"""
from __future__ import annotations
import json
import os
import numpy as np
import config as C
import geo
import demand
from simulate import Sim, dispatch_footprint


def build_data(alpha=None, seed=None, max_agents=5000):
    alpha = C.ALPHA_EMPIRICAL if alpha is None else alpha
    seed = C.BASE_SEED if seed is None else seed
    sim = Sim()
    sd = sim.sdict
    cluster = geo.ntu_cluster()
    od = demand.origin_od_table(cluster)
    caps = dispatch_footprint(cluster)
    disp_set = set(caps)
    Vw, Vb, tau = sim.p["V_WALK"], sim.p["V_BIKE"], sim.p["TAU"]

    rng = np.random.default_rng(seed)
    lam = np.array([r.get("eff_lambda", r["lambda_base"]) for r in od])
    counts = rng.poisson(alpha * lam)
    idx = np.repeat(np.arange(len(counts)), counts)
    n = len(idx)
    if n == 0:
        raise SystemExit("no agents")
    arrival = rng.uniform(*C.SIM_WINDOW, size=n)
    order = np.argsort(arrival, kind="stable")

    b_ni = {g: int(round(c)) for g, c in caps.items()}
    b_wi = {g: int(round(c)) for g, c in caps.items()}

    def leg(a, b, mode):
        (lo1, la1), (lo2, la2) = sd[a], sd[b]
        d = geo.manhattan_m(lo1, la1, lo2, la2)
        dur = d / (Vb if mode == 1 else Vw)
        return [round(la1, 6), round(lo1, 6), round(la2, 6), round(lo2, 6), round(dur, 1), mode]

    agents = []
    for a in order:
        r = idx[a]; i, j = od[r]["origin"], od[r]["dst"]
        dij = sim.dist(i, j); tol = tau * dij
        # 無資訊
        m = sim.nearest_station(i)
        if m in disp_set and b_ni[m] > 0:
            b_ni[m] -= 1; ni = [leg(i, m, 0), leg(m, j, 1)]; nis = True
        else:
            ni = [leg(i, m, 0), leg(m, j, 0)]; nis = False
        # 有資訊：容忍內、有餘量的最近調度站
        best, bestd = None, 1e18
        for g in caps:
            if b_wi[g] > 0:
                dig = sim.dist(i, g)
                if dig <= tol and dig < bestd:
                    best, bestd = g, dig
        if best is not None:
            b_wi[best] -= 1; wi = [leg(i, best, 0), leg(best, j, 1)]; wis = True
        else:
            wi = [leg(i, j, 0)]; wis = False
        agents.append({"t": round(float(arrival[a]), 1), "ni": ni, "wi": wi,
                       "nis": nis, "wis": wis})

    if len(agents) > max_agents:
        sel = rng.choice(len(agents), max_agents, replace=False)
        agents = [agents[k] for k in sorted(sel)]

    clon, clat, _ = (sd[C.CLUSTER_CENTER][0], sd[C.CLUSTER_CENTER][1], None)
    goal = sd[C.GOAL_STATION]
    cmax = max(caps.values()) if caps else 1
    data = {
        "center": [clat, clon], "zoom": 15,
        "window": [C.SIM_WINDOW[0], C.SIM_WINDOW[1]],
        "goal": [goal[1], goal[0]],
        "dispatch": [[sd[g][1], sd[g][0], round(c, 1), round(c / cmax, 3)] for g, c in caps.items()],
        "agents": agents,
        "alpha": alpha, "shortage": alpha / (1 + alpha),
        "n": len(agents), "total_cap": round(sum(caps.values())),
    }
    return data


HTML = r"""<!DOCTYPE html><html lang="zh-Hant"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>YouBike 調度資訊模擬 — agent 移動動畫</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
 body{margin:0;font-family:"Noto Sans CJK TC","PingFang TC",sans-serif;background:#f4f4f4;color:#222}
 #bar{padding:8px 14px;background:#fff;box-shadow:0 1px 4px rgba(0,0,0,.15);display:flex;
      align-items:center;gap:14px;flex-wrap:wrap}
 #bar h1{font-size:16px;margin:0 12px 0 0}
 button{font-size:14px;padding:5px 14px;border:0;border-radius:6px;background:#2e75b6;color:#fff;cursor:pointer}
 button:hover{background:#1f5e96}
 .clock{font-variant-numeric:tabular-nums;font-weight:bold}
 #wrap{display:flex;gap:6px;padding:6px}
 .pane{flex:1;position:relative}
 .map{height:78vh;border-radius:8px}
 .ttl{position:absolute;top:8px;left:50%;transform:translateX(-50%);z-index:500;background:rgba(255,255,255,.92);
      padding:4px 14px;border-radius:14px;font-weight:bold;font-size:15px;box-shadow:0 1px 3px rgba(0,0,0,.2)}
 .stat{position:absolute;bottom:10px;left:10px;z-index:500;background:rgba(255,255,255,.92);
      padding:8px 12px;border-radius:8px;font-size:13px;line-height:1.5;box-shadow:0 1px 3px rgba(0,0,0,.2)}
 .lgd{position:absolute;bottom:10px;right:10px;z-index:500;background:rgba(255,255,255,.92);
      padding:6px 10px;border-radius:8px;font-size:12px}
 .dot{display:inline-block;width:10px;height:10px;border-radius:50%;margin-right:5px;vertical-align:middle}
 input[type=range]{vertical-align:middle}
</style></head><body>
<div id="bar">
 <h1>YouBike 調度資訊模擬</h1>
 <button id="play">播放</button>
 <button id="reset">重來</button>
 <span>速度 <input id="spd" type="range" min="0.3" max="4" step="0.1" value="1.5"></span>
 <span class="clock" id="clk">17:00</span>
 <span id="meta" style="color:#666"></span>
</div>
<div id="wrap">
 <div class="pane"><div class="ttl" style="color:#b03030">未取得資訊 without info</div>
   <div id="mapL" class="map"></div>
   <div class="stat" id="stL"></div>
   <div class="lgd"><span class="dot" style="background:#888"></span>走路
     <span class="dot" style="background:#2e9b46;margin-left:8px"></span>騎車
     <span class="dot" style="background:#2e75b6;border-radius:2px;margin-left:8px"></span>調度站</div></div>
 <div class="pane"><div class="ttl" style="color:#1f7a1f">取得資訊 with info</div>
   <div id="mapR" class="map"></div>
   <div class="stat" id="stR"></div></div>
</div>
<script>
const D = __DATA__;
const TILE='https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png';
function mk(id){const m=L.map(id,{zoomControl:true,attributionControl:false}).setView(D.center,D.zoom);
  L.tileLayer(TILE,{maxZoom:19,subdomains:'abcd'}).addTo(m);return m;}
const mapL=mk('mapL'),mapR=mk('mapR');
// 同步兩圖視角
let syncing=false;
function sync(a,b){a.on('move',()=>{if(syncing)return;syncing=true;b.setView(a.getCenter(),a.getZoom(),{animate:false});syncing=false;});}
sync(mapL,mapR);sync(mapR,mapL);
// 調度站 + Goal
function deco(m){
  D.dispatch.forEach(d=>{L.circleMarker([d[0],d[1]],{radius:4+8*d[3],color:'#1f4e79',weight:1,
     fillColor:'#2e75b6',fillOpacity:.85}).addTo(m).bindTooltip('調度站 '+d[2]+' 台/窗');});
  L.marker([D.goal[0],D.goal[1]]).addTo(m).bindTooltip('Goal 公館');
}
deco(mapL);deco(mapR);
// 預建 agent markers
function build(m){return D.agents.map(()=>L.circleMarker([0,0],{radius:4,weight:0,
   fillColor:'#888',fillOpacity:0}).addTo(m));}
const mkL=build(mapL),mkR=build(mapR);
// 每個 agent 每情境的總時長
function tot(legs){let s=0;for(const l of legs)s+=l[4];return s;}
D.agents.forEach(a=>{a.niT=tot(a.ni);a.wiT=tot(a.wi);});
const W0=D.window[0],W1=D.window[1],WIN=W1-W0;
const maxT=Math.max(...D.agents.map(a=>Math.max(a.niT,a.wiT)));
const END=W1+maxT;
// 動畫：WIN 壓縮到 ~26 秒
let simT=W0,playing=false,last=null,speed=1.5;
const ANIM=26000; // ms 對應整個 WIN
function fmt(t){t=Math.max(W0,Math.min(t,W1));const mm=Math.floor(t/60);
  return String(Math.floor(mm/60)).padStart(2,'0')+':'+String(mm%60).padStart(2,'0');}
function posOf(a,legs,T){ // 回傳 [lat,lon,mode] 或 null(未開始/已結束)
  let e=T-a.t; if(e<0)return null;
  for(const l of legs){ if(e<=l[4]){const f=l[4]>0?e/l[4]:1;
     return [l[0]+(l[2]-l[0])*f, l[1]+(l[3]-l[1])*f, l[5]];} e-=l[4]; }
  return 'done';
}
function frame(ts){
  if(playing){ if(last!==null){const dw=ts-last; simT+=dw/ANIM*WIN*speed;} last=ts; }
  else last=ts;
  if(simT>END){simT=END;playing=false;document.getElementById('play').textContent='播放';}
  let nL=0,cL=0,sL=0, nR=0,cR=0,sR=0;
  for(let k=0;k<D.agents.length;k++){
    const a=D.agents[k];
    upd(mkL[k],posOf(a,a.ni,simT));
    upd(mkR[k],posOf(a,a.wi,simT));
    // 統計：已抵達者
    if(simT-a.t>=a.niT){nL++;cL+=a.niT;if(a.nis)sL++;}
    if(simT-a.t>=a.wiT){nR++;cR+=a.wiT;if(a.wis)sR++;}
  }
  document.getElementById('clk').textContent=fmt(simT);
  document.getElementById('stL').innerHTML=stat('未取得資訊',nL,cL,sL);
  document.getElementById('stR').innerHTML=stat('取得資訊',nR,cR,sR);
  requestAnimationFrame(frame);
}
function upd(mk,p){
  if(p===null||p==='done'){mk.setStyle({fillOpacity:p==='done'?0.12:0});return;}
  mk.setLatLng([p[0],p[1]]);
  mk.setStyle({fillOpacity:.9,fillColor:p[2]===1?'#2e9b46':'#888',radius:p[2]===1?4.5:4});
}
function stat(name,n,csum,s){
  const avg=n?(csum/n/60):0;
  return '<b>'+name+'</b><br>已抵達 '+n+' / '+D.agents.length+
    '<br>借到車 '+s+'，占 '+(n?Math.round(100*s/n):0)+'%'+
    '<br>平均 cost <b>'+avg.toFixed(1)+'</b> 分';
}
document.getElementById('meta').textContent='缺車比例 '+(D.shortage*100).toFixed(0)+
  '%　agent '+D.n+' 人　真實調度 '+D.total_cap+' 台/窗　cost 另含還車側、動畫未繪';
document.getElementById('play').onclick=function(){playing=!playing;last=null;
  this.textContent=playing?'暫停':'播放';};
document.getElementById('reset').onclick=function(){simT=W0;playing=false;last=null;
  document.getElementById('play').textContent='播放';};
document.getElementById('spd').oninput=function(){speed=parseFloat(this.value);};
requestAnimationFrame(frame);
</script></body></html>"""


def main():
    data = build_data()
    html = HTML.replace("__DATA__", json.dumps(data, separators=(",", ":")))
    out = os.path.join(C.RESULTS, "anim.html")
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"  -> {out}  (agent={data['n']}, 缺車比例={data['shortage']*100:.0f}%)")


if __name__ == "__main__":
    main()
