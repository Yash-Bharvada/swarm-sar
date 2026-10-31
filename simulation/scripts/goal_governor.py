"""Experimental local decision overrides; never modifies actor weights or logits."""
from collections import Counter, deque


class GoalGovernor:
    def __init__(self, mode, commitment=12, stall_limit=4, loop_window=16):
        if mode not in ('persistence','loop','combined'):raise ValueError(mode)
        self.mode=mode; self.commitment=commitment; self.stall_limit=stall_limit
        self.positions=deque(maxlen=loop_window); self.goals=deque(maxlen=loop_window)
        self.goal=None; self.started=0; self.last_position=None; self.stalled=0
        self.counts=Counter()

    def choose(self, proposed, *, position, candidates, mask, step):
        position=tuple(position)
        self.stalled=self.stalled+1 if position==self.last_position else 0
        self.last_position=position; self.positions.append(position)
        legal={i:c for i,c in enumerate(candidates[:5]) if mask[i]>0 and len(c['path'])>=2}
        old=next((i for i,c in legal.items() if tuple(c['position'])==self.goal),None)
        action=proposed; reason='policy'
        # Preserve explicit investigation and hold semantics. This experiment
        # addresses switched movement goals, not the separate excessive-HOLD issue.
        if proposed<5 and old is not None and self.mode in ('persistence','combined'):
            if step-self.started<self.commitment and self.stalled<self.stall_limit:
                action=old; reason='goal_persistence' if action!=proposed else 'policy'
        # Repeated directed edges indicate oscillation. Backtracking remains legal
        # unless a less-repeated legal next step exists; never force HOLD to escape.
        edges=Counter(zip(list(self.positions)[:-1],list(self.positions)[1:]))
        if action in legal and self.mode in ('loop','combined'):
            target=tuple(legal[action]['path'][1]); edge_count=edges[(position,target)]
            if edge_count>=2:
                alternatives=[i for i,c in legal.items() if tuple(c['path'][1])!=target and edges[(position,tuple(c['path'][1]))]<edge_count]
                if alternatives:
                    action=min(alternatives,key=lambda i:(edges[(position,tuple(legal[i]['path'][1]))],self.positions.count(tuple(legal[i]['path'][1])),self.goals.count(tuple(legal[i]['position'])),legal[i]['distance'],i))
                    reason='loop_escape'
                else:self.counts['loop_without_alternative']+=1
        if action in legal:
            goal=tuple(legal[action]['position'])
            if goal!=self.goal:self.goal=goal;self.started=step
            self.goals.append(goal)
        elif position==self.goal:
            self.goal=None
        self.counts['decisions']+=1
        if action!=proposed:self.counts['overrides']+=1;self.counts[reason]+=1
        return action,reason
