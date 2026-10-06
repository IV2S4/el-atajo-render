"""Dibuja el póster del ecosistema AUTONOMON a partir de los flujos de n8n.
Uso: python mapa/mapa.py <pedido.json> <salida.html>
El pedido puede traer los flujos crudos de la API de n8n (nodes + connections)
o ya compactos ({n, a, nodes:[[nombre,tipo,x,y]], edges:[[a,b,k]]})."""
import json, sys, re, datetime

ZONA = {}
for n in (5, 8, 14, 12, 13, 6, 0): ZONA[n] = 'canal'
for n in (15, 16, 17, 18, 19, 20): ZONA[n] = 'din'
for n in (1, 2, 3, 9, 10, 11): ZONA[n] = 'asis'
for n in (4, 7): ZONA[n] = 'man'
FILAS = [[5], [8], [14], [1, 3], [19, 15, 16], [18, 17, 20], [12, 13, 6], [10, 9, 11], [2, 7, 4]]
MESES = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto',
         'septiembre', 'octubre', 'noviembre', 'diciembre']


def compactar(w):
    if 'edges' in w:
        return w
    ns = [n for n in w.get('nodes', []) if not n.get('type', '').endswith('stickyNote')]
    idx = {n['name']: i for i, n in enumerate(ns)}
    nodes = [[n['name'], n['type'].split('.')[-1], round(n['position'][0]), round(n['position'][1])] for n in ns]
    edges = []
    for src, kinds in (w.get('connections') or {}).items():
        for kind, salidas in kinds.items():
            for lista in salidas or []:
                for t in lista or []:
                    if src in idx and t.get('node') in idx:
                        edges.append([idx[src], idx[t['node']], 0] if kind == 'main' else [idx[t['node']], idx[src], 1])
    return {'n': w['name'], 'a': bool(w.get('active')), 'nodes': nodes, 'edges': edges}


def main(entrada, salida):
    datos = json.load(open(entrada, encoding='utf-8'))
    if isinstance(datos, dict):
        datos = datos.get('flujos') or datos.get('data') or []
    flujos = [compactar(w) for w in datos if not w.get('isArchived') and w.get('nodes')]
    por_num, sueltos = {}, []
    for w in flujos:
        m = re.match(r'\s*(\d+)', w['n'])
        if m and int(m.group(1)) not in por_num:
            num = int(m.group(1))
            w['z'] = ZONA.get(num, 'man')
            por_num[num] = w
        else:
            w['z'] = 'man'
            sueltos.append(w)
    filas, usados = [], set()
    for fila in FILAS:
        f = [n for n in fila if n in por_num]
        if f:
            filas.append(f)
            usados.update(f)
    resto = sorted(n for n in por_num if n not in usados)
    claves = {}
    for n in resto:
        claves['f%d' % n] = por_num[n]
    for i, w in enumerate(sueltos):
        claves['s%d' % i] = w
    extra = ['f%d' % n for n in resto] + ['s%d' % i for i in range(len(sueltos))]
    w_map = {str(n): w for n, w in por_num.items()}
    w_map.update(claves)
    filas = [[str(n) for n in f] for f in filas]
    for i in range(0, len(extra), 3):
        filas.append(extra[i:i + 3])
    hoy = datetime.datetime.utcnow() - datetime.timedelta(hours=4)  # hora de Puerto Rico
    fecha = '%d de %s de %d' % (hoy.day, MESES[hoy.month - 1], hoy.year)
    tpl = open(__file__.replace('mapa.py', 'plantilla.html'), encoding='utf-8').read()
    html = (tpl.replace('__DATA__', json.dumps({'rows': filas, 'w': w_map}, ensure_ascii=False))
               .replace('__NF__', str(len(flujos)))
               .replace('__NA__', str(sum(1 for w in flujos if w['a'])))
               .replace('__FECHA__', fecha))
    open(salida, 'w', encoding='utf-8').write(html)
    print('flujos:', len(flujos), 'activos:', sum(1 for w in flujos if w['a']))


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
