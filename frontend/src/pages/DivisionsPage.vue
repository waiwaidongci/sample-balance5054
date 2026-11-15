<script setup lang="ts">
import{ref,computed,onMounted,watch}from 'vue';
import{samples,loadBatches}from '../stores/samples';
import{isAdmin}from '../stores/auth';
import{getVersions,createVersion,getRatioEdges,saveRatioMap,getDrafts,createDraft,publishDraft}from '../api/divisions';
import type{DivisionVersion,RatioEdge,RatioRow,ConversionDraft,ConversionRefusal}from '../types/domain';
import{useTask}from '../hooks/useTask';
import{number,dateTime}from '../utils/format';
import PageHeading from '../components/common/PageHeading.vue';
import BatchSelect from '../components/BatchSelect.vue';
import ErrorNotice from '../components/common/ErrorNotice.vue';
import StatusBadge from '../components/common/StatusBadge.vue';
import EmptyState from '../components/common/EmptyState.vue';

const versions=ref<DivisionVersion[]>([]),edges=ref<RatioEdge[]>([]),drafts=ref<ConversionDraft[]>([]);
const{error,busy,execute}=useTask();
const versionForm=ref({code:'',name:'',is_current:false});
const edgeForm=ref<{from_version_id:number;to_version_id:number;rows:RatioRow[]}>({from_version_id:0,to_version_id:0,rows:[]});
const draftForm=ref({batch_id:1,from_version_id:0,to_version_id:0});
const active=ref<ConversionDraft|null>(null),refusal=ref<ConversionRefusal|null>(null);
const savedEdge=ref(false),published=ref(false);

const vName=(id:number)=>versions.value.find(v=>v.id===id)?.name??'#'+id;
const currentVersion=computed(()=>versions.value.find(v=>v.is_current));
const sourceZones=computed(()=>active.value?Object.keys(active.value.payload.source).sort():[]);
const targetZones=computed(()=>active.value?Object.keys(active.value.payload.converted).sort():[]);
const cell=(s:string,t:string)=>{const share=active.value?.payload.matrix[s]?.[t];return share===undefined||!active.value?null:share*active.value.payload.source[s]};
const edgeTotals=computed(()=>{const totals:Record<string,number>={};for(const r of edgeForm.value.rows)if(r.from_zone)totals[r.from_zone]=(totals[r.from_zone]??0)+(Number(r.ratio)||0);return totals});

const refreshMeta=()=>execute(async()=>{[versions.value,edges.value]=await Promise.all([getVersions(),getRatioEdges()])});
const refreshDrafts=async()=>{drafts.value=await getDrafts(draftForm.value.batch_id)};
const addVersion=()=>execute(async()=>{await createVersion(versionForm.value);versionForm.value={code:'',name:'',is_current:false};await refreshMeta()});
const editEdge=(edge:RatioEdge)=>{savedEdge.value=false;edgeForm.value={from_version_id:edge.from_version_id,to_version_id:edge.to_version_id,rows:edge.rows.map(r=>({...r}))}};
const newEdge=()=>{savedEdge.value=false;edgeForm.value={from_version_id:versions.value[0]?.id??0,to_version_id:currentVersion.value?.id??0,rows:[{from_zone:'',to_zone:'',ratio:1}]}};
const addRow=()=>edgeForm.value.rows.push({from_zone:'',to_zone:'',ratio:1});
const saveEdge=()=>execute(async()=>{
  const rows=edgeForm.value.rows;
  if(!edgeForm.value.from_version_id||!edgeForm.value.to_version_id)throw new Error('请选择起止版本');
  if(rows.some(r=>!r.from_zone.trim()||!r.to_zone.trim()||!(r.ratio>0)||r.ratio>1))throw new Error('比例行需要新旧区划与(0,1]内的比例');
  if(new Set(rows.map(r=>r.from_zone+'→'+r.to_zone)).size!==rows.length)throw new Error('同一对区划的比例重复');
  await saveRatioMap(edgeForm.value.from_version_id,edgeForm.value.to_version_id,rows.map(r=>({from_zone:r.from_zone.trim(),to_zone:r.to_zone.trim(),ratio:Number(r.ratio)})));
  savedEdge.value=true;await refreshMeta();await refreshDrafts();
});
const generate=()=>execute(async()=>{
  refusal.value=null;active.value=null;published.value=false;
  try{active.value=await createDraft(draftForm.value.batch_id,draftForm.value.from_version_id,draftForm.value.to_version_id);await refreshDrafts()}
  catch(e){const payload=(e as{payload?:unknown}).payload;if(payload&&typeof payload==='object'&&Array.isArray((payload as ConversionRefusal).involved))refusal.value=payload as ConversionRefusal;else throw e}
});
const view=(draft:ConversionDraft)=>{refusal.value=null;published.value=false;active.value=draft};
const publish=(id:number)=>execute(async()=>{const r=await publishDraft(id);active.value=r.draft;published.value=true;await Promise.all([refreshDrafts(),loadBatches()])});

watch(()=>draftForm.value.batch_id,()=>{active.value=null;refusal.value=null;published.value=false;execute(refreshDrafts)});
onMounted(()=>execute(async()=>{
  await Promise.all([loadBatches(),refreshMeta()]);
  if(samples.batches.length)draftForm.value.batch_id=samples.batches[0].id;
  draftForm.value.from_version_id=versions.value.find(v=>!v.is_current)?.id??versions.value[0]?.id??0;
  draftForm.value.to_version_id=currentVersion.value?.id??0;
  edgeForm.value.to_version_id=currentVersion.value?.id??0;
  await refreshDrafts();
}));
</script>
<template>
<PageHeading index="05" title="区划版本的拆并换算" subtitle="旧区目标按登记比例换算到现行区划；人口守恒、全程不取整，核对人数后再发布整套目标。"/>
<ErrorNotice :message="error" @retry="refreshMeta"/>

<div class="section-heading"><h2>版本台账</h2><span v-if="currentVersion">现行区划：{{currentVersion.name}}</span></div>
<div class="table-wrap"><table><thead><tr><th>编码</th><th>名称</th><th>已登记区划</th><th>现行</th></tr></thead>
<tbody><tr v-for="v in versions" :key="v.id"><td><strong>{{v.code}}</strong></td><td>{{v.name}}</td><td>{{v.zones.join('、')||'—'}}</td><td><span v-if="v.is_current" class="badge published">现行</span></td></tr></tbody></table></div>
<form v-if="isAdmin" class="form-strip" @submit.prevent="addVersion">
<label class="grow">版本编码<input v-model="versionForm.code" placeholder="如 d2030" pattern="[a-z0-9-]{2,30}" required/></label>
<label class="grow">版本名称<input v-model="versionForm.name" placeholder="如 2030试点区划" maxlength="60" required/></label>
<label>设为现行<input type="checkbox" v-model="versionForm.is_current" style="width:auto"/></label>
<button :disabled="busy">登记版本</button>
</form>

<div class="section-heading"><h2>拆并比例</h2><span>每个旧区划的去向比例合计必须为1（人口守恒）</span></div>
<EmptyState v-if="!edges.length&&!edgeForm.rows.length" title="还没有比例映射" hint="机构更换区划后，先登记相邻版本间的拆并比例，再换算目标。"/>
<div v-if="edges.length" class="table-wrap"><table><thead><tr><th>映射</th><th>修订号</th><th>行数</th><th>守恒核对</th><th v-if="isAdmin"></th></tr></thead>
<tbody><tr v-for="e in edges" :key="e.from_version_id+'-'+e.to_version_id"><td><strong>{{e.from_name}} → {{e.to_name}}</strong></td><td>#{{e.revision}}</td><td>{{e.rows.length}}</td><td><span v-if="!e.problems.length" class="badge published">守恒</span><span v-else class="badge stale" :title="e.problems.join('；')">不守恒</span></td><td v-if="isAdmin"><a href="javascript:;" @click="editEdge(e)">编辑</a></td></tr></tbody></table></div>
<form v-if="isAdmin" @submit.prevent="saveEdge">
<div class="form-grid">
<label>起始版本<select v-model.number="edgeForm.from_version_id" required><option v-for="v in versions" :key="v.id" :value="v.id">{{v.name}}</option></select></label>
<label>目标版本<select v-model.number="edgeForm.to_version_id" required><option v-for="v in versions" :key="v.id" :value="v.id">{{v.name}}</option></select></label>
</div>
<div v-if="edgeForm.rows.length" class="table-wrap"><table><thead><tr><th>旧区划</th><th>新区划</th><th>比例</th><th>旧区合计</th><th></th></tr></thead>
<tbody><tr v-for="(row,i) in edgeForm.rows" :key="i">
<td><input v-model="row.from_zone" aria-label="旧区划" maxlength="30" required/></td>
<td><input v-model="row.to_zone" aria-label="新区划" maxlength="30" required/></td>
<td><input v-model.number="row.ratio" aria-label="比例" type="number" min="0.000001" max="1" step="any" required/></td>
<td><span v-if="edgeTotals[row.from_zone]!==undefined" class="badge" :class="Math.abs(edgeTotals[row.from_zone]-1)<=1e-9?'published':'stale'">{{number(edgeTotals[row.from_zone],6)}}</span></td>
<td><button type="button" @click="edgeForm.rows.splice(i,1)">删行</button></td>
</tr></tbody></table></div>
<div class="form-actions"><button type="button" @click="addRow">加一行</button><button type="button" @click="newEdge">新建映射</button><button class="primary" :disabled="busy||!edgeForm.rows.length">保存比例（修订号+1）→</button><p v-if="savedEdge" class="success">比例已保存；依赖旧比例的草案已失效。</p></div>
</form>

<div class="section-heading"><h2>换算草案与人数核对</h2><span>原始区划 → 现行区划，逐级不取整</span></div>
<div class="toolbar"><BatchSelect v-model="draftForm.batch_id" :items="samples.batches"/><span v-if="!isAdmin">当前角色只读；由抽样负责人生成草案并发布。</span></div>
<form v-if="isAdmin" class="form-strip" @submit.prevent="generate">
<label class="grow">旧目标口径版本<select v-model.number="draftForm.from_version_id" required><option v-for="v in versions" :key="v.id" :value="v.id">{{v.name}}</option></select></label>
<label class="grow">换算目标版本<select v-model.number="draftForm.to_version_id" required><option v-for="v in versions" :key="v.id" :value="v.id">{{v.name}}</option></select></label>
<button class="primary" :disabled="busy||!draftForm.from_version_id||!draftForm.to_version_id">生成换算草案 →</button>
</form>
<div v-if="refusal" class="error" role="alert">换算被拒绝：{{refusal.message}}
<ul style="margin:10px 0 0;padding-left:20px"><li v-for="(item,i) in refusal.involved" :key="i">{{[item.version,item.from_version&&item.to_version?item.from_version+'→'+item.to_version:'',item.zone,item.total!==undefined?'合计 '+number(item.total,6):''].filter(Boolean).join(' · ')}}</li></ul>
</div>
<section v-if="active" class="reviewed" style="border-left-color:var(--red)">
<p><strong>草案 #{{active.id}} · {{active.from_label}} → {{active.to_label}}</strong> <StatusBadge :status="active.status"/></p>
<p>换算路径：<span v-for="(path,i) in active.payload.paths" :key="i">{{i?'；':''}}{{path.map(vName).join(' → ')}}</span></p>
<div class="table-wrap"><table><thead><tr><th>原始区划 \ 现行区划</th><th v-for="t in targetZones" :key="t">{{t}}</th><th>行合计</th></tr></thead>
<tbody>
<tr v-for="s in sourceZones" :key="s"><td><strong>{{s}}</strong></td><td v-for="t in targetZones" :key="t" :title="String(cell(s,t)??'')">{{cell(s,t)===null?'—':number(cell(s,t)!,2)}}</td><td :title="String(active.payload.source[s])">{{number(active.payload.source[s],2)}}</td></tr>
<tr><td><strong>列合计</strong></td><td v-for="t in targetZones" :key="t" :title="String(active.payload.converted[t])"><strong>{{number(active.payload.converted[t],2)}}</strong></td><td :title="String(active.payload.converted_total)"><strong>{{number(active.payload.converted_total,2)}}</strong></td></tr>
</tbody></table></div>
<p>人口守恒：原始总计 {{number(active.payload.source_total,2)}} ＝ 现行总计 {{number(active.payload.converted_total,2)}}。显示保留两位小数，存储与计算不取整。</p>
<div v-if="isAdmin&&active.status==='draft'" class="form-actions"><button class="primary" :disabled="busy" @click="publish(active.id)">核对无误，发布整套目标 →</button></div>
<p v-if="published" class="success">整套目标已发布：分区边际替换为现行区划口径，其余维度保持不变；历史校准结果不受影响。</p>
</section>

<div class="section-heading"><h2>草案记录</h2><button @click="execute(refreshDrafts)">刷新 ↻</button></div>
<EmptyState v-if="!drafts.length" title="还没有换算草案" hint="选择批次与起止版本后生成草案；修订比例会使依赖它的草案失效。"/>
<div v-else class="table-wrap"><table><thead><tr><th>编号</th><th>换算</th><th>状态</th><th>原始总计 → 现行总计</th><th>创建时间</th><th></th></tr></thead>
<tbody><tr v-for="d in drafts" :key="d.id">
<td class="mono">#{{d.id}}</td><td><strong>{{d.from_label}} → {{d.to_label}}</strong></td><td><StatusBadge :status="d.status"/></td>
<td>{{number(d.payload.source_total,2)}} → {{number(d.payload.converted_total,2)}}</td><td>{{dateTime(d.created_at)}}</td>
<td><a href="javascript:;" @click="view(d)">核对</a><template v-if="isAdmin&&d.status==='draft'"> · <a href="javascript:;" @click="publish(d.id)">发布</a></template></td>
</tr></tbody></table></div>
<p class="method-note">同一起止版本若经不同路径换算结果不一致、版本映射存在循环或区划缺少去向，换算被拒绝并列出涉及区划。发布在事务内重算比例指纹，与修订并发时不会混用新旧比例；发布只更新目标边际，不回写历史校准运行。</p>
</template>
