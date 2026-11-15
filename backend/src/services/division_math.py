"""区划版本拆并换算的纯计算：多级传播、人口守恒、全程不取整。

版本为节点、登记的比例映射为有向边。换算沿起止版本间的每条简单路径传播人口，
结果必须路径无关；存在循环、缺少去向、比例不守恒或路径间不一致时拒绝使用，
并在 involved 中列出涉及的区划/版本。本模块不做任何取整。
"""
from collections import defaultdict

MAX_PATHS=128
TOLERANCE=1e-9

class ConversionError(Exception):
    def __init__(self,reason,message,involved):
        super().__init__(message)
        self.reason=reason
        self.involved=involved

def _reachable(adjacency,start,allowed=None):
    seen=set();stack=[start]
    while stack:
        node=stack.pop()
        for nxt in adjacency.get(node,()):
            if (allowed is None or nxt in allowed) and nxt not in seen:
                seen.add(nxt);stack.append(nxt)
    return seen

def _cycle_nodes(adjacency,nodes):
    involved=set()
    for node in nodes:
        for nxt in adjacency.get(node,()):
            if nxt in nodes and node in _reachable(adjacency,nxt,nodes):
                involved.add(node);involved.add(nxt)
    return involved

def _paths(adjacency,source,target,nodes,label):
    found=[];stack=[(source,[source])]
    while stack:
        node,path=stack.pop()
        if node==target:
            found.append(path)
            if len(found)>MAX_PATHS:raise ConversionError('too_many_paths','起止版本间路径超过%d条，图过于复杂，拒绝换算'%(MAX_PATHS),[{'version':label(v)} for v in sorted(nodes)])
            continue
        for nxt in adjacency.get(node,()):
            if nxt in nodes and nxt not in path:stack.append((nxt,path+[nxt]))
    return found

def convert_populations(edges,source,target,populations,names=None):
    """edges: {(from_version,to_version): {from_zone: {to_zone: ratio}}}；
    populations: {source_zone: population}。返回换算结果、转移矩阵与所用路径。"""
    names=names or {}
    def label(v):return names.get(v,str(v))
    if source==target:raise ConversionError('same_version','起止版本不能相同',[])
    if not populations:raise ConversionError('empty','没有可换算的分区人口',[])
    adjacency={}
    for frm,to in edges:adjacency.setdefault(frm,set()).add(to)
    forward=_reachable(adjacency,source);forward.add(source)
    reversed_adj={}
    for frm,to in edges:reversed_adj.setdefault(to,set()).add(frm)
    backward=_reachable(reversed_adj,target);backward.add(target)
    relevant=forward&backward
    if target not in forward:
        raise ConversionError('no_destination','版本间缺少去向：无法从%s换算到%s'%(label(source),label(target)),[{'version':label(source),'zone':z} for z in sorted(populations)])
    cyclic=_cycle_nodes(adjacency,relevant)
    if cyclic:
        raise ConversionError('cycle','版本映射存在循环，拒绝换算：'+'、'.join(label(v) for v in sorted(cyclic)),[{'version':label(v)} for v in sorted(cyclic)])
    paths=_paths(adjacency,source,target,relevant,label)
    used_edges=sorted({(p[i],p[i+1]) for p in paths for i in range(len(p)-1)})
    offend=[]
    for edge in used_edges:
        for zone,dests in sorted(edges[edge].items()):
            total=sum(dests.values())
            if abs(total-1)>TOLERANCE:offend.append({'from_version':label(edge[0]),'to_version':label(edge[1]),'zone':zone,'total':total})
    if offend:
        raise ConversionError('not_conserved','拆并比例不守恒（人口合计必须为1）：'+'；'.join('%s→%s 的 %s 合计 %.6f'%(o['from_version'],o['to_version'],o['zone'],o['total']) for o in offend),offend)
    def propagate(path,vector):
        current={z:float(v) for z,v in vector.items()}
        for i in range(len(path)-1):
            mapping=edges[(path[i],path[i+1])]
            missing=sorted(z for z in current if z not in mapping)
            if missing:
                raise ConversionError('no_destination','缺少去向：%s 在 %s→%s 没有登记拆并比例'%('、'.join(missing),label(path[i]),label(path[i+1])),[{'version':label(path[i]),'zone':z} for z in missing])
            nxt=defaultdict(float)
            for zone,amount in current.items():
                for dest,ratio in mapping[zone].items():nxt[dest]+=amount*ratio
            current=dict(nxt)
        return current
    results=[propagate(path,populations) for path in paths]
    zones=set().union(*(r.keys() for r in results))
    base=max(1.0,abs(sum(populations.values())))
    diff=sorted(z for z in zones if max(r.get(z,0.0) for r in results)-min(r.get(z,0.0) for r in results)>TOLERANCE*base)
    if diff:
        raise ConversionError('inconsistent','同一起止版本经%d条路径换算结果不一致，涉及区划：%s'%(len(paths),'、'.join(diff)),[{'zone':z} for z in diff])
    matrix={zone:propagate(paths[0],{zone:1.0}) for zone in populations}
    converted=defaultdict(float)
    for zone,amount in populations.items():
        for dest,share in matrix[zone].items():converted[dest]+=amount*share
    return {'converted':dict(converted),'matrix':{z:dict(row) for z,row in matrix.items()},'paths':paths,'used_edges':[list(e) for e in used_edges],'source_total':sum(populations.values()),'converted_total':sum(converted.values())}
