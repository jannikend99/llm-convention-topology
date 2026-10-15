"""Descriptive pilot rehearsal; gate carry is a display assumption, not new observations.

Run from the experiment checkout: python -m convention_topology.analysis.pilot
--campaign data/runs/pilot-run-n48-cap1500 --output /absolute/pilot/path
"""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
import subprocess
import sys
import PIL
from collections import Counter, deque
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation, PillowWriter
import networkx as nx
import numpy as np

from convention_topology.analysis.stream import artifact_paths, refuse_pickle_jsonl_mismatch

WINDOW, OWN, STEP = 144, 12, 24
CHECKPOINTS = (144, 288, 576, 864)


def modal(values):
    """Unique mode and modal share; ties remain unassigned."""
    counts = Counter(values)
    if not counts:
        return None, None, False
    maximum = max(counts.values())
    winners = [lab for lab, count in counts.items() if count == maximum]
    return (winners[0] if len(winners) == 1 else None), maximum / len(values), len(winners) > 1


def own_states(histories, t, committed_label=None):
    result = {}
    for node, history in histories.items():
        recent = list(history)[-OWN:]
        name, share, tie = modal([lab for _, lab in recent])
        result[node] = dict(name=name, modal_share=share, tie=tie, empty=not recent,
                            count=len(recent), short=len(recent) < OWN,
                            oldest_age=t-recent[0][0] if recent else None,
                            newest_age=t-recent[-1][0] if recent else None,
                            committed_share=sum(lab == committed_label for _, lab in recent)/len(recent)
                            if recent and committed_label else None)
    return result


def components(graph, states):
    groups = []
    for name in sorted({s['name'] for s in states.values() if s['name'] is not None}):
        nodes = [v for v, s in states.items() if s['name'] == name]
        for members in sorted(nx.connected_components(graph.subgraph(nodes)), key=lambda x: min(x)):
            groups.append((name, set(members)))
    return groups


def overlap_records(old, new, old_groups, new_groups, old_counts, new_counts):
    """All overlapping successors; denominator excludes unassigned states at either time."""
    rows = []
    assigned_both = {v for v in old if old[v]['name'] is not None and new[v]['name'] is not None}
    for i, (name, original) in enumerate(old_groups):
        observable = original & assigned_both
        name_retained = sum(new[v]['name'] == name for v in observable)
        common = dict(baseline_group=i, baseline_name=name, baseline_size=len(original),
                      observable_members=len(observable), coverage=len(observable)/len(original),
                      name_retained=name_retained,
                      name_retention=name_retained/len(observable) if observable else None,
                      new_decisions=sum(new_counts[v]-old_counts[v] for v in observable),
                      members_with_new_decision=sum(new_counts[v]>old_counts[v] for v in observable),
                      members_with_12_new_decisions=sum(new_counts[v]-old_counts[v]>=OWN for v in observable))
        successors = [(j, label, members) for j, (label, members) in enumerate(new_groups)
                      if observable & members]
        for j, label, members in successors or [(None, None, set())]:
            later_observable = members & assigned_both
            shared = observable & later_observable
            rows.append(dict(common, successor_group=j, successor_name=label,
                             successor_size=len(members), shared_members=len(shared),
                             member_continuity=len(shared)/len(observable) if observable else None,
                             jaccard=len(shared)/len(observable | later_observable)
                             if observable | later_observable else None))
    return rows


def derive(rows, meta, graph):
    histories = {v: deque(maxlen=OWN) for v in graph}
    counts = Counter({v: 0 for v in graph})
    cm = set(meta.get('committed_ids') or [])
    target = meta.get('committed_to') if meta['program'] == 'cm' else None
    flexible = set(graph)-cm
    endpoints = set(range(STEP, len(rows)+1, STEP)) | {len(rows)}
    checkpoints = set(CHECKPOINTS) & set(range(1, len(rows)+1)) | ({len(rows)} if rows else set())
    labels, success, flexible_labels = Counter(), 0, Counter()
    window = deque()
    first_flip = None
    trajectory, states_table, local_table, groups_table, persistence = [], [], [], [], []
    previous = None
    for t, row in enumerate(rows, 1):
        pair = [(int(row['p1']), row['label_p1']), (int(row['p2']), row['label_p2'])]
        if row['t'] != t or not graph.has_edge(pair[0][0], pair[1][0]):
            raise ValueError(f"invalid time or pair at {meta['run_id']} t={t}")
        if bool(row['success']) != (pair[0][1] == pair[1][1]):
            raise ValueError('success disagrees with emitted labels')
        for node, label in pair:
            histories[node].append((t, label)); counts[node] += 1; labels[label] += 1
            if node in flexible: flexible_labels[label] += 1
        success += int(row['success']); window.append((pair, int(row['success'])))
        if len(window)>WINDOW:
            old_pair, old_success = window.popleft(); success -= old_success
            for node, label in old_pair:
                labels[label] -= 1
                if node in flexible: flexible_labels[label] -= 1
        name, dominance, tie = modal(list(labels.elements()))
        if target and len(window)==WINDOW and success>=137 and name==target and first_flip is None:
            first_flip = t
        if t not in endpoints and t not in checkpoints: continue
        states = own_states(histories, t, target)
        assigned_flexible = [v for v in flexible if states[v]['name'] is not None]
        uptake_n = sum(states[v]['name']==target for v in flexible) if target else None
        eligible_edges = [(a,b) for a,b in graph.edges if states[a]['name'] is not None and states[b]['name'] is not None]
        agreeing = sum(states[a]['name']==states[b]['name'] for a,b in eligible_edges)
        groups = components(graph, states)
        base = dict(t=t, full_window=len(window)==WINDOW,
                    success_count=success if len(window)==WINDOW else None,
                    success_share=success/WINDOW if len(window)==WINDOW else None,
                    dominant_name=name if len(window)==WINDOW else None,
                    dominant_share=dominance if len(window)==WINDOW else None,
                    flexible_committed_count=flexible_labels[target] if target and len(window)==WINDOW else None,
                    flexible_emissions=sum(flexible_labels.values()) if target and len(window)==WINDOW else None,
                    flexible_production=flexible_labels[target]/sum(flexible_labels.values())
                    if target and len(window)==WINDOW and sum(flexible_labels.values()) else None,
                    flexible_agents=len(flexible), uptake_count=uptake_n,
                    uptake_share=uptake_n/len(flexible) if target else None,
                    flexible_assigned=len(assigned_flexible),
                    flexible_tied=sum(states[v]['tie'] for v in flexible),
                    flexible_empty=sum(states[v]['empty'] for v in flexible),
                    assigned=sum(s['name'] is not None for s in states.values()),
                    agreeing_edges=agreeing, assigned_edges=len(eligible_edges),
                    neighbour_agreement=agreeing/len(eligible_edges) if eligible_edges else None,
                    largest_component=max((len(g) for _,g in groups), default=0))
        if t in endpoints: trajectory.append(base)
        if t in checkpoints:
            local_table.append(base)
            for node, s in states.items():
                states_table.append(dict(t=t,node=node,scripted=node in cm,total_own_decisions=counts[node],**s))
            for i, (label,members) in enumerate(groups):
                groups_table.append(dict(t=t,group=i,name=label,size=len(members),members=' '.join(map(str,sorted(members)))))
            if previous:
                old_t, old_states, old_groups, old_counts = previous
                persistence.extend(dict(from_t=old_t,to_t=t,**r) for r in overlap_records(old_states,states,old_groups,groups,old_counts,counts))
            previous = (t,states,groups,counts.copy())
    final = trajectory[-1] if trajectory else {}
    return dict(first_flip=first_flip, final=final, trajectory=trajectory, states=states_table,
                local=local_table, groups=groups_table, persistence=persistence)


def write_csv(path, rows):
    keys = list(dict.fromkeys(k for row in rows for k in row))
    with path.open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=keys)
        writer.writeheader(); writer.writerows(rows)


def load_rows(path, meta):
    pickle_path, event_path = artifact_paths(path)
    _, rows, _ = refuse_pickle_jsonl_mismatch(meta=meta,meta_path=path,pickle_path=pickle_path,events_path=event_path)
    return rows


def plot_summary(manifest, trajectories, out):
    for model in sorted({m['model'] for m in manifest}):
        fig, axes = plt.subplots(1,3,figsize=(15,4))
        for ax, program, field, title in [(axes[0],'emergence','final_dominance','Study 1: endpoint concentration'),
                                          (axes[1],'cm','strict_flip','Study 2: strict flip (completed only)'),
                                          (axes[2],'cm','final_flexible_production','Study 2: endpoint flexible production')]:
            cells = sorted({(m['topology'],m['k']) for m in manifest if m['model']==model and m['program']==program})
            for x, (top,k) in enumerate(cells):
                subset = [m for m in manifest if m['model']==model and m['program']==program and m['topology']==top and m['k']==k and m['endpoint_eligible']]
                values = [m[field] for m in subset if m[field] is not None]
                ax.scatter([x]*len(values), values, alpha=.35, s=15)
                if values: ax.plot(x,np.mean(values),'k_',ms=15)
                ax.text(x,1.03,f'n={len(values)}',ha='center',fontsize=7)
            ax.set_xticks(range(len(cells)),[f'{top}\nk={k}' if k else top for top,k in cells],rotation=65,ha='right',fontsize=7)
            ax.set_ylim(-.03,1.12);ax.set_title(title,fontsize=10);ax.set_ylabel('Run-level share / flip indicator')
        fig.suptitle(f'PROVISIONAL PILOT — {model}; individual runs and mean; no tests')
        fig.tight_layout();fig.savefig(out/f'{model}_endpoints.png',dpi=150);plt.close(fig)
        fig, axes = plt.subplots(1,2,figsize=(12,4))
        for ax, field, title in [(axes[0],'flexible_production','Committed-name flexible emission share'),(axes[1],'uptake_share','Current flexible-agent modal uptake')]:
            cells=sorted({(m['topology'],m['k']) for m in manifest if m['model']==model and m['program']=='cm'})
            for top,k in cells:
                eligible={m['run_id'] for m in manifest if m['model']==model and m['program']=='cm' and m['topology']==top and m['k']==k and m['endpoint_eligible']}
                times=sorted({r['t'] for r in trajectories if r['run_id'] in eligible and r.get(field) is not None})
                vals=[[r[field] for r in trajectories if r['run_id'] in eligible and r['t']==t and r.get(field) is not None] for t in times]
                ax.plot(times,[np.mean(v) for v in vals],label=f'{top} k{k} n={len(eligible)}')
            ax.set_title(title);ax.set_xlabel('Network interactions');ax.set_ylim(-.02,1.02)
        axes[1].legend(fontsize=6,loc='upper left',bbox_to_anchor=(1,1));fig.suptitle(f'PROVISIONAL PILOT — {model}; completion-conditional run means')
        fig.tight_layout();fig.savefig(out/f'{model}_cm_trajectories.png',dpi=150);plt.close(fig)


def lattice_positions(graph):
    """Circular positions for the recorded nearest/next-nearest degree-four ring."""
    nodes = sorted(graph)
    expected = {tuple(sorted((nodes[i], nodes[(i+d) % len(nodes)])))
                for i in range(len(nodes)) for d in (1, 2)}
    if {tuple(sorted(edge)) for edge in graph.edges} != expected:
        raise ValueError('Curved-ring layout requires the recorded nearest/next-nearest ring.')
    return nx.circular_layout(nodes)


def draw_lattice_edges(graph, pos, ax):
    """Draw all actual ring edges as inward curves; second neighbours bend more."""
    from matplotlib.path import Path as MplPath
    from matplotlib.patches import PathPatch
    nodes = sorted(graph)
    indices = {node: i for i, node in enumerate(nodes)}
    drawn = []
    for a, b in graph.edges:
        distance = abs(indices[a]-indices[b])
        distance = min(distance, len(nodes)-distance)
        if distance not in (1, 2):
            raise ValueError('Unexpected edge in nearest/next-nearest ring.')
        start, end = np.asarray(pos[a]), np.asarray(pos[b])
        control = (start+end)/2 * (.82 if distance == 1 else .48)
        curve = MplPath([start, control, end],
                        [MplPath.MOVETO, MplPath.CURVE3, MplPath.CURVE3])
        ax.add_patch(PathPatch(curve, facecolor='none',
                               edgecolor='#999999' if distance == 1 else '#566574',
                               linewidth=1 if distance == 1 else 1.15, alpha=.8))
        drawn.append((a, b))
    return drawn


def animation(meta,rows,graph,path):
    target=meta.get('committed_to') if meta['program']=='cm' else None
    cm=set(meta.get('committed_ids') or [])
    labels=sorted({r[k] for r in rows for k in ('label_p1','label_p2')})
    palette={lab:plt.get_cmap('tab10')(i%10) for i,lab in enumerate(labels)}
    nodes=sorted(graph);is_lattice=meta['topology']=='lattice'
    pos=lattice_positions(graph) if is_lattice else nx.spring_layout(graph,seed=42)
    times=list(range(STEP,len(rows)+1,STEP))
    if rows and (not times or times[-1]!=len(rows)):times.append(len(rows))
    histories={v:deque(maxlen=OWN) for v in nodes};frames=[];cursor=0
    for t in times:
        for r in rows[cursor:t]:
            histories[int(r['p1'])].append((r['t'],r['label_p1']));histories[int(r['p2'])].append((r['t'],r['label_p2']))
        frames.append(own_states(histories,t,target));cursor=t
    fig,(ax,curve)=plt.subplots(2,1,figsize=(8,9),gridspec_kw={'height_ratios':[3,1]})
    series=[]
    for t,states in zip(times,frames):
        win=rows[max(0,t-WINDOW):t]
        if target:
            emissions=[r['label_p'+str(j)] for r in win for j in (1,2) if int(r['p'+str(j)]) not in cm]
            production=sum(x==target for x in emissions)/len(emissions) if len(win)==WINDOW and emissions else float('nan')
            uptake=sum(states[v]['name']==target for v in nodes if v not in cm)/(len(nodes)-len(cm))
            series.append((production,uptake))
        else:
            _,dom,_=modal([r['label_p'+str(j)] for r in win for j in (1,2)])
            series.append((sum(r['success'] for r in win)/WINDOW if len(win)==WINDOW else float('nan'),dom if len(win)==WINDOW else float('nan')))
    def draw(index):
        ax.clear();curve.clear();states=frames[index]
        shown=series[:index+1]
        curve.plot(times[:index+1],[x[0] for x in shown],label='Flexible emission share' if target else 'Pair success (144)',color=palette[target] if target else '#0072B2')
        curve.plot(times[:index+1],[x[1] for x in shown],label='Current flexible-agent uptake' if target else 'Global concentration (144)',color='black' if target else '#D55E00',linestyle='--' if target else '-')
        curve.set_xlim(0,len(rows));curve.set_ylim(-.03,1.03);curve.set_xlabel('Observed network interactions');curve.set_ylabel('Share');curve.legend(fontsize=8,loc='upper left');curve.axvline(times[index],color='grey',lw=.7)
        if is_lattice:
            draw_lattice_edges(graph,pos,ax)
        else:
            nx.draw_networkx_edges(graph,pos,ax=ax,alpha=.025 if graph.number_of_edges()>300 else .18,width=.5)
        for v in nodes:
            s=states[v];color=palette[s['name']] if s['name'] else ('#a0a0a0' if s['tie'] else 'white')
            nx.draw_networkx_nodes(graph,pos,nodelist=[v],node_color=[color],node_size=150,
                                   node_shape='s' if v in cm else 'o',edgecolors='black' if v in cm else '#777777',
                                   linewidths=2 if v in cm else .5,alpha=.55 if s['short'] else 1,ax=ax)
        ax.set_title(f"PROVISIONAL PILOT {meta['model_shorthand']} {meta['topology']} k={meta.get('cm_k')}\nt={times[index]} / observed end {len(rows)}; {meta['run_status']}\nOwn last≤12: grey=tied, white=empty, pale=short; squares=scripted",fontsize=10)
        if is_lattice:
            for v in nodes:
                x, y = pos[v]
                ax.text(x*1.07, y*1.07, str(v), ha='center', va='center', fontsize=6)
            ax.set_xlim(-1.18,1.18);ax.set_ylim(-1.2,1.22);ax.set_aspect('equal')
            ax.text(.5,.98,'Curved ring: shallow arcs = direct neighbours; deeper arcs = next-nearest',
                    transform=ax.transAxes,ha='center',va='top',fontsize=8)
        ax.axis('off')
        from matplotlib.patches import Patch
        ax.legend(handles=[Patch(color=c,label=lab) for lab,c in palette.items()],loc='upper center' if is_lattice else 'lower left',bbox_to_anchor=(.5,-.01) if is_lattice else None,fontsize=8,ncol=min(5,len(palette)) if is_lattice else 1)
    draw(0)
    fig.tight_layout()
    FuncAnimation(fig,draw,frames=len(frames),interval=200).save(path,writer=PillowWriter(fps=5));plt.close(fig)


def additional_displays(manifest, outputs, h4, tables, figures):
    """Run-level descriptive summaries and timing/local displays for the first review."""
    from collections import defaultdict
    eligible = {m['run_id'] for m in manifest if m['endpoint_eligible']}
    rng = np.random.default_rng(20260930)
    summaries = []
    fields = ('success_share', 'dominant_share', 'flexible_production', 'uptake_share',
              'neighbour_agreement', 'largest_component_assigned_share', 'assignment_coverage')
    for source in ('trajectories', 'local_checkpoints'):
        grouped = defaultdict(list)
        for original in outputs[source]:
            if original['run_id'] not in eligible:
                continue
            r = dict(original)
            r['largest_component_assigned_share'] = r['largest_component']/r['assigned'] if r['assigned'] else None
            r['assignment_coverage'] = r['assigned']/48
            grouped[(r['model'], r['program'], r['topology'], r['k'], r['t'])].append(r)
        for key, runs in sorted(grouped.items()):
            for field in fields:
                values = np.array([r[field] for r in runs if r.get(field) is not None], dtype=float)
                if not len(values):
                    continue
                low = high = None
                if len(values) >= 2:
                    boot = rng.choice(values, (1000, len(values)), replace=True).mean(axis=1)
                    low, high = map(float, np.quantile(boot, [.025, .975]))
                summaries.append(dict(source=source, model=key[0], program=key[1], topology=key[2],
                                      k=key[3], t=key[4], measure=field, n=len(values),
                                      mean=float(values.mean()), interval_low=low, interval_high=high,
                                      interval='descriptive run bootstrap; conditional on eligibility/observation'))
    # Display-only summaries retain verified gate endpoints; raw source rows stay observed.
    for source in ('trajectories', 'local_checkpoints'):
        raw_display = [dict(r, assumed_stable=False) for r in outputs[source]
                   if r['run_id'] in eligible and r['program']=='emergence']
        by_run = defaultdict(list)
        for r in raw_display: by_run[r['run_id']].append(r)
        horizons={m['run_id']:int(m['expected_horizon']) for m in manifest if m['run_id'] in eligible and m['program']=='emergence'}
        display=[r for r in raw_display if r['t']==horizons[r['run_id']] or (r['t']%STEP==0 if source=='trajectories' else r['t'] in CHECKPOINTS)]
        for m in manifest:
            if m['run_id'] not in eligible or m['program']!='emergence' or m['stop_reason']!='gate': continue
            rows = by_run[m['run_id']]
            end = next(r for r in rows if r['t']==m['observed_end'])
            times = sorted(set(range(STEP,int(m['expected_horizon'])+1,STEP) if source=='trajectories' else CHECKPOINTS)|{int(m['expected_horizon'])})
            for t in times:
                if m['observed_end']<t<=m['expected_horizon']:
                    display.append(dict(end,t=t,assumed_stable=True))
        grouped=defaultdict(list)
        for r in display:
            r['largest_component_assigned_share']=r['largest_component']/r['assigned'] if r['assigned'] else None
            r['assignment_coverage']=r['assigned']/48
            grouped[(r['model'],r['program'],r['topology'],r['k'],r['t'])].append(r)
        for key, rows in sorted(grouped.items()):
            for field in fields:
                valid=[r for r in rows if r.get(field) is not None]
                values=np.array([r[field] for r in valid],dtype=float)
                if not len(values):continue
                low=high=None
                if len(values)>=2:
                    boot=rng.choice(values,(1000,len(values)),replace=True).mean(axis=1)
                    low,high=map(float,np.quantile(boot,[.025,.975]))
                summaries.append(dict(source=source+'_gate_carry',model=key[0],program=key[1],topology=key[2],k=key[3],t=key[4],measure=field,n=len(values),observed_n=sum(not r['assumed_stable'] for r in valid),carried_n=sum(r['assumed_stable'] for r in valid),mean=float(values.mean()),interval_low=low,interval_high=high,interval='descriptive run bootstrap; post-gate stability assumed'))
    write_csv(tables/'run_level_summaries.csv', summaries)

    for model in sorted({m['model'] for m in manifest}):
        # Shared-time Study-1 summaries; non-grid endpoints remain in endpoint tables.
        fig, axes = plt.subplots(1, 2, figsize=(11, 4))
        for ax, field, title in zip(axes, ('success_share', 'dominant_share'),
                                   ('Pair success', 'Global emission concentration')):
            for top in sorted({m['topology'] for m in manifest}):
                rs = [r for r in summaries if r['model']==model and r['program']=='emergence'
                      and r['source']=='trajectories_gate_carry' and r['topology']==top
                      and r['measure']==field and (r['t'] % STEP==0 or r['t']==1500)]
                ax.plot([r['t'] for r in rs], [r['mean'] for r in rs], label=top)
                # Do not fabricate a confidence interval for one contributing run.
                ax.fill_between([r['t'] for r in rs],
                                [r['interval_low'] if r['interval_low'] is not None else np.nan for r in rs],
                                [r['interval_high'] if r['interval_high'] is not None else np.nan for r in rs], alpha=.1)
            ax.set_title(title); ax.set_ylim(-.03, 1.03); ax.set_xlabel('Network interactions')
        axes[1].legend(fontsize=7)
        fig.suptitle(f'PROVISIONAL PILOT — {model}; gate endpoints held, assuming stability; observed/carried n in CSV')
        fig.tight_layout(); fig.savefig(figures/f'{model}_study1_trajectories.png', dpi=150); plt.close(fig)

        fig, axes = plt.subplots(1, 2, figsize=(11, 4))
        for ax, selection in zip(axes, ('all_unique_modal', 'majority_gt_50pct')):
            rs = [r for r in h4 if r['model']==model and r['selection']==selection]
            ax.bar([r['name'] for r in rs], [r['count'] for r in rs])
            ax.tick_params(axis='x', rotation=60); ax.set_ylabel('Runs')
            ax.set_title(('All unique endpoint modes' if selection=='all_unique_modal' else 'Endpoint majority >50%')
                         + f"; n={rs[0]['denominator'] if rs else 0}")
        fig.suptitle(f'PROVISIONAL PILOT — {model}, mixing Study 1; ties and eligible totals in CSV')
        fig.tight_layout(); fig.savefig(figures/f'{model}_h4_names.png', dpi=150); plt.close(fig)

        cm_runs = [m for m in manifest if m['model']==model and m['program']=='cm']
        ks = sorted({m['k'] for m in cm_runs})
        fig, axes = plt.subplots(len(ks), 2, figsize=(12, 4*len(ks)), squeeze=False)
        for row_index, k in enumerate(ks):
            ax, cumulative = axes[row_index]
            subset = sorted([m for m in cm_runs if m['k']==k], key=lambda m:(m['topology'], m['run_id']))
            tops = sorted({m['topology'] for m in subset})
            colours = {top: plt.get_cmap('tab10')(i) for i, top in enumerate(tops)}
            for y, r in enumerate(subset):
                ax.plot([0, r['observed_end']], [y, y], color=colours[r['topology']], lw=.7, alpha=.5)
                if r['first_flip_t'] is not None:
                    ax.scatter(r['first_flip_t'], y, color='black', s=8)
                if not r['endpoint_eligible']:
                    ax.scatter(r['observed_end'], y, marker='x', color='red', s=12)
            ax.set_title(f'k={k}: each line a run; dot=first flip, red x=technical/invalid end')
            ax.set_yticks([]); ax.set_xlabel('Network interactions')
            for top in tops:
                rs = [r for r in subset if r['topology']==top and r['endpoint_eligible']]
                if not rs:
                    continue
                horizon = rs[0]['expected_horizon']
                ts = sorted({0, horizon} | {r['first_flip_t'] for r in rs if r['first_flip_t'] is not None})
                ys = [sum(r['first_flip_t'] is not None and r['first_flip_t'] <= t for r in rs)/len(rs) for t in ts]
                cumulative.step(ts, ys, where='post', color=colours[top], label=f'{top} n={len(rs)}')
            cumulative.set_title(f'k={k}: first flip by time, completed runs only')
            cumulative.set_ylim(-.03, 1.03); cumulative.set_xlabel('Observed network interactions'); cumulative.legend(fontsize=6)
        fig.suptitle(f'PROVISIONAL PILOT — {model}; completion-conditional curves, prefixes kept separate')
        fig.tight_layout(); fig.savefig(figures/f'{model}_flip_timing.png', dpi=150); plt.close(fig)

        fig, axes = plt.subplots(1, 2, figsize=(12, 4))
        for ax, field, title in zip(axes, ('neighbour_agreement', 'largest_component_assigned_share'),
                                   ('Neighbour-name agreement', 'Largest same-name region / assigned agents')):
            keys = sorted({(r['program'], r['topology'], r['k']) for r in summaries if r['model']==model})
            for program, top, k in keys:
                rs = [r for r in summaries if r['model']==model and r['source']==('local_checkpoints_gate_carry' if program=='emergence' else 'local_checkpoints')
                      and r['program']==program and r['topology']==top and r['k']==k
                      and r['measure']==field and (r['t'] in CHECKPOINTS or program=='emergence' and r['t']==1500)]
                ax.plot([r['t'] for r in rs], [r['mean'] for r in rs], marker='.',
                        label=f'{program} {top} k{k}' if k else f'{program} {top}')
            ax.set_title(title); ax.set_ylim(-.03, 1.03); ax.set_xlabel('Network interactions')
        axes[1].legend(fontsize=5, bbox_to_anchor=(1, 1), loc='upper left')
        fig.suptitle(f'PROVISIONAL PILOT — {model}; last <=12 own choices; S1 gate states held (assumption); observed/carried n in CSV')
        fig.tight_layout(); fig.savefig(figures/f'{model}_local_structure.png', dpi=150); plt.close(fig)


def selftest():
    assert modal([])==(None,None,False)
    assert modal(['a','b'])==(None,.5,True)
    assert modal(['a','a','b'])==('a',2/3,False)
    g=nx.path_graph([1,2,3,4]);h={i:deque([(1,'a')],maxlen=12) for i in g}
    old=own_states(h,1);new=own_states({i:deque([(2,'b')],maxlen=12) for i in g},2)
    r=overlap_records(old,new,components(g,old),components(g,new),Counter({i:1 for i in g}),Counter({i:2 for i in g}))[0]
    assert r['name_retention']==0 and r['member_continuity']==1
    split=dict(new);split[3]=dict(new[3],name='c');split[4]=dict(new[4],name='c')
    assert len(overlap_records(old,split,components(g,old),components(g,split),Counter({i:1 for i in g}),Counter({i:2 for i in g})))==2
    merged=overlap_records(split,new,components(g,split),components(g,new),Counter({i:2 for i in g}),Counter({i:3 for i in g}))
    assert len(merged)==2 and all(r['member_continuity']==1 for r in merged)
    long={1:deque([(t,'a' if t<=40 else 'b') for t in range(1,53)],maxlen=12)}
    assert own_states(long,52)[1]['name']=='b'
    assert own_states({1:deque()},0)[1]['empty']
    rows=[dict(t=t,p1=1,p2=2,label_p1='b',label_p2='b',success=True) for t in range(1,145)]
    m=dict(program='cm',committed_ids=[1],committed_to='b',run_id='test')
    d=derive(rows,m,nx.path_graph([1,2]));assert d['first_flip']==144
    assert d['final']['flexible_emissions']==144 and d['final']['flexible_production']==1
    d=derive(rows[:100],m,nx.path_graph([1,2]));assert d['first_flip'] is None and d['trajectory'][-1]['t']==100
    print('Constructed checks passed: empty/tie/short, name change, split, strict flip, scripted exclusion, stopped prefix.')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--campaign',type=Path);parser.add_argument('--output',type=Path)
    parser.add_argument('--self-test',action='store_true');parser.add_argument('--animations',type=int,default=2)
    args=parser.parse_args();selftest()
    if args.self_test and not args.campaign:return
    if not args.campaign or not args.output:parser.error('--campaign and --output required')
    campaign=args.campaign.resolve();out=args.output.resolve();tables=out/'tables';figures=out/'figures'
    tables.mkdir(parents=True,exist_ok=True);figures.mkdir(parents=True,exist_ok=True)
    rawgraphs=json.loads((campaign/'graphs.json').read_text());graphs={}
    if rawgraphs['N'] != 48: raise ValueError('This pilot recipe requires N=48; review rules before changing N.')
    for name,item in rawgraphs['graphs'].items():
        g=nx.Graph();g.add_nodes_from(range(1,rawgraphs['N']+1));g.add_edges_from(item['adjacency']);graphs[name]=g
    pool=json.loads((campaign/'label_pool.json').read_text())
    if isinstance(pool,dict): pool=pool.get('labels',pool.get('label_pool',[]))
    manifest=[];outputs={name:[] for name in ['trajectories','agent_states','local_checkpoints','components','group_changes']};paths={}
    for index,p in enumerate(sorted((campaign/'runs').rglob('*.meta.json'))):
        meta=json.loads(p.read_text());rows=load_rows(p,meta);graph=graphs[meta['topology']];d=derive(rows,meta,graph)
        program=meta['program'];terminal=meta['run_status'] in ('completed','censored')
        eligible=(terminal and len(rows)>=WINDOW) if program=='emergence' else (meta['run_status']=='completed' and len(rows)>=WINDOW and len(rows)==meta['phase2_horizon'] and meta.get('prepared_state_valid') is True)
        context=dict(run_id=meta['run_id'],model=meta['model_shorthand'],program=program,topology=meta['topology'],k=meta.get('cm_k') or 0)
        final=d['final'];entry=dict(context,status=meta['run_status'],stop_reason=meta.get('stop_reason'),observed_end=len(rows),expected_horizon=meta.get('phase2_horizon') or meta.get('cap_phase1'),endpoint_eligible=eligible,eligibility_reason='usable terminal endpoint' if eligible else 'technical/nonterminal or insufficient/invalid endpoint',first_flip_t=d['first_flip'],strict_flip=int(d['first_flip'] is not None) if program=='cm' else None,final_dominance=final.get('dominant_share'),final_success=final.get('success_share'),final_dominant_name=final.get('dominant_name'),final_flexible_production=final.get('flexible_production'),final_uptake=final.get('uptake_share'),recorded_prepared_valid=meta.get('prepared_state_valid'))
        manifest.append(entry);paths[meta['run_id']]=p
        for key,source in [('trajectories','trajectory'),('agent_states','states'),('local_checkpoints','local'),('components','groups'),('group_changes','persistence')]:
            outputs[key].extend(dict(context,endpoint_eligible=eligible,**r) for r in d[source])
        if (index+1)%100==0:print(f'Derived {index+1} runs',flush=True)
    write_csv(tables/'run_manifest.csv',manifest)
    for name,rows in outputs.items():write_csv(tables/f'{name}.csv',rows)
    cells=[]
    for cell in sorted({(r['model'],r['program'],r['topology'],r['k']) for r in manifest}):
        subset=[r for r in manifest if (r['model'],r['program'],r['topology'],r['k'])==cell];eligible=[r for r in subset if r['endpoint_eligible']]
        cells.append(dict(model=cell[0],program=cell[1],topology=cell[2],k=cell[3],attempted=len(subset),eligible=len(eligible),**{s:sum(r['status']==s for r in subset) for s in ['completed','censored','failed','interrupted']},flipped_eligible=sum(r['strict_flip'] or 0 for r in eligible),flip_rate=sum(r['strict_flip'] or 0 for r in eligible)/len(eligible) if eligible and cell[1]=='cm' else None))
    write_csv(tables/'cell_coverage.csv',cells)
    h4=[]
    for model in sorted({r['model'] for r in manifest}):
        candidates=[r for r in manifest if r['model']==model and r['program']=='emergence' and r['topology']=='mixing' and r['endpoint_eligible']]
        for selection in ('all_unique_modal','majority_gt_50pct'):
            selected=[r for r in candidates if r['final_dominant_name'] is not None and (selection=='all_unique_modal' or r['final_dominance']>.5)]
            counts=Counter(r['final_dominant_name'] for r in selected)
            for label in sorted(pool):
                count=counts[label]
                h4.append(dict(model=model,selection=selection,name=label,count=count,denominator=len(selected),share=count/len(selected) if selected else None,eligible_total=len(candidates),tied_endpoints=sum(r['final_dominant_name'] is None for r in candidates)))
    write_csv(tables/'h4_names.csv',h4);plot_summary(manifest,outputs['trajectories'],figures)
    additional_displays(manifest, outputs, h4, tables, figures)
    selections=[]
    # First select one typical complete trajectory per cell, then rotate topology/model
    # so animation limits do not silently favour sorted cells or extreme outcomes.
    candidate_cells=sorted({(r['model'],r['program'],r['topology'],r['k']) for r in manifest})
    ordered=sorted(candidate_cells,key=lambda c:(['lattice','random_regular','barabasi_albert','watts_strogatz','mixing'].index(c[2]),c[1],c[0],c[3]))
    review_order = sorted(ordered, key=lambda c:(0 if (c[1]=='emergence' and c[2]=='lattice' and c[0]=='gemma4_31b') else 1 if (c[1]=='cm' and c[2]=='lattice' and c[0]=='gemma4_31b' and c[3]==12) else 2, ordered.index(c)))
    for cell in review_order if args.animations>0 else []:
        rs=[r for r in manifest if (r['model'],r['program'],r['topology'],r['k'])==cell and r['endpoint_eligible']]
        if not rs:continue
        field='final_flexible_production' if cell[1]=='cm' else 'final_dominance'
        median=float(np.median([r[field] for r in rs]));chosen=min(rs,key=lambda r:(abs(r[field]-median),r['run_id']))
        selections.append(dict(chosen,selection='typical: closest endpoint production/concentration to cell median',cell_median=median))
        if len(selections)>=args.animations:break
    # Additional contrasting examples come from the same first CM cell if present.
    cm_cells=[c for c in review_order if c[1]=='cm']
    if cm_cells and args.animations>0:
        cell=cm_cells[0];rs=[r for r in manifest if (r['model'],r['program'],r['topology'],r['k'])==cell and r['endpoint_eligible'] and not r['strict_flip']]
        if rs:
            for name,key in [('contrary: greatest endpoint flexible production among completed no-flip runs',lambda r:(-r['final_flexible_production'],r['run_id'])),('uneventful: least endpoint flexible production among completed no-flip runs',lambda r:(r['final_flexible_production'],r['run_id']))]:
                selected=min(rs,key=key)
                if selected['run_id'] not in {r['run_id'] for r in selections}:selections.append(dict(selected,selection=name))
    write_csv(tables/'animation_selection.csv',selections)
    for selected in selections:
        p=paths[selected['run_id']];meta=json.loads(p.read_text());rows=load_rows(p,meta)
        print('Animating '+selected['run_id'],flush=True);animation(meta,rows,graphs[meta['topology']],figures/(selected['run_id']+'.gif'))
    revision=subprocess.run(['git','rev-parse','HEAD'],capture_output=True,text=True).stdout.strip()
    provenance=dict(campaign=str(campaign),output=str(out),code_revision=revision, environment=dict(python=sys.version, numpy=np.__version__, networkx=nx.__version__, matplotlib=matplotlib.__version__, pillow=PIL.__version__), local_changes=subprocess.run(['git','status','--short'],capture_output=True,text=True).stdout.splitlines(),producer_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),recipe=dict(window=WINDOW,own_decisions=OWN,curve_step=STEP,checkpoints=CHECKPOINTS),runs=len(manifest),self_tests='passed',limits=['Provisional pilot only; no Main estimates or formal hypothesis tests.','Technical prefixes appear in trajectories but not fixed-horizon comparisons.','Prepared memories excluded from own observed states; stream/prompt joins not audited here.','Neighbour/component summaries include scripted nodes, with flags; uptake excludes them.','No spatial shuffle null yet. Run-bootstrap intervals in summary tables; some initial plots show distributions/means only.','Group changes compare adjacent observed checkpoints; shared members, not causal or binary persistence.','Animation selection is illustrative and recorded; layout proximity is not an edge.'])
    (out/'producer_provenance.json').write_text(json.dumps(provenance,indent=2)+'\n')
    print(f'Completed {len(manifest)} runs; outputs {out}',flush=True)


if __name__=='__main__':main()
