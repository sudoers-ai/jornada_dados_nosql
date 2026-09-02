import sys
from streamlit.testing.v1 import AppTest
at = AppTest.from_file("/app/viz/painel.py", default_timeout=180)
at.run()
print("exceptions:", len(at.exception))
for e in at.exception:
    print("  ❌", e.value)
print("warnings streamlit:", len(at.warning))
for w in at.warning[:6]:
    print("  ⚠️ ", str(w.value)[:160])
print("erros na pagina:", len(at.error))
for e in at.error[:6]:
    print("  ❌", str(e.value)[:160])
print("metricas renderizadas:", len(at.metric))
for m in at.metric[:4]:
    print(f"   {m.label}: {m.value}")
print("dataframes:", len(at.dataframe), "| tabs:", len(at.tabs))
sys.exit(1 if (at.exception or at.error) else 0)
