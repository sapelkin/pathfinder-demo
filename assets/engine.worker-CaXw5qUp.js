const o=e=>self.postMessage(e),u=[];let m=!1,g=null,d=null,y=null;async function _(e,n){const t=await fetch(e);if(!t.ok)throw new Error(`${n}: ${t.status} ${t.statusText} for ${e}`);const s=Number(t.headers.get("content-length")||0);if(!t.body||!s)return t.arrayBuffer();const p=t.body.getReader(),h=[];let r=0;for(;;){const{done:i,value:l}=await p.read();if(i)break;h.push(l),r+=l.length,o({type:"progress",stage:n,loaded:r,total:s})}const a=new Uint8Array(r);let f=0;for(const i of h)a.set(i,f),f+=i.length;return a.buffer}async function x(e,n){const t=self.location.origin,s=new URL(e,t).href,p=new URL("pyodide/",s).href;o({type:"progress",stage:"Loading the engine… 10 MB, once"}),await _(new URL("pyodide.asm.wasm",p).href,"Python runtime");const h=await import(new URL("pyodide.mjs",p).href);o({type:"progress",stage:"Starting Python"});const r=await h.loadPyodide({indexURL:p});o({type:"progress",stage:"Installing the engine"});const a=await(await fetch(new URL("engine/manifest.json",s).href,{cache:"no-cache"})).json(),f=await _(new URL(`engine/${a.wheel}`,s).href,"Engine");if(r.unpackArchive(f,"whl"),a.stubDispatch)try{const c=await(await fetch(new URL("engine/dispatch.py",s).href)).text();await r.runPythonAsync(`import importlib.util, pathlib, pathfinder_engine
_p = pathlib.Path(pathfinder_engine.__file__).parent / "dispatch.py"
if not _p.exists():
    _p.write_text(${JSON.stringify(c)})`)}catch{}await r.runPythonAsync(`
import json
from pathfinder_engine import __version__ as _engine_version
from pathfinder_engine.dispatch import Dispatcher
_dispatcher = Dispatcher()

def _handle(method, path, query_json, body_json):
    r = _dispatcher.handle(method, path, json.loads(query_json), json.loads(body_json) if body_json else None)
    return json.dumps(r, separators=(",", ":"))

def _export():
    return _dispatcher.export_document()

def _import(text):
    try:
        _dispatcher.import_document(text)
        return ""
    except Exception as e:  # noqa: BLE001
        return f"{type(e).__name__}: {e}"
`),g=r.globals.get("_handle"),d=r.globals.get("_export"),y=r.globals.get("_import");let i=!1;if(n){const c=y(n);i=!c,c&&console.warn("Stored document not restored:",c)}const l=await r.runPythonAsync("_engine_version");for(m=!0,o({type:"ready",engine:String(l),stubDispatch:a.stubDispatch,restored:i});u.length;)await b(u.shift())}async function b(e){if(!(!g||!d||!y)){if(e.type==="call"){const n=g(e.method,e.path,JSON.stringify(e.query),e.body===void 0?"":JSON.stringify(e.body)),t=JSON.parse(n);o({type:"result",id:e.id,status:t.status,body:t.body}),e.method==="POST"&&t.status<400&&o({type:"document",text:d()})}else if(e.type==="export")o({type:"exported",id:e.id,text:d()});else if(e.type==="import"){const n=y(e.text);o({type:"imported",id:e.id,ok:!n,error:n||void 0}),n||o({type:"document",text:d()})}}}let w=Promise.resolve();self.onmessage=e=>{const n=e.data;if(n.type==="init"){x(n.baseURL,n.document).catch(t=>o({type:"fatal",message:t instanceof Error?t.message:String(t)}));return}if(!m){u.push(n);return}w=w.then(()=>b(n)).catch(t=>{n.type==="call"&&o({type:"result",id:n.id,status:500,body:{error:t instanceof Error?t.message:String(t)}})})};
