"""Local completion review using only the actor's visible observations/history.

No task evaluator or database access. Inner calls must be logged by the supplied
backend. Rejected proposals are never executed or silently edited into answers.
"""
import ast
import json
from .prompting import parse_json_object

REVIEW_PROMPT = '''Review a browser agent's proposed completion against the user's goal,
CURRENT page observation and executed action history. Ignore the actor's own claim
that it succeeded. You are not deciding whether the task is possible.
Return ONLY {"allow_finish": true_or_false, "reason": "short specific reason"}.

First classify the GOAL, not the proposed answer. "View the status", "read the price"
and "find the SKU" ask for existing field values; they do NOT ask to change those
fields. Accept the matching field value without requiring any edit/save.
History target metadata quotes the control AS IT WAS OBSERVED at action time.
A historical click targeting a button labeled Save is a save attempt even if its bid
is different on the current page after navigation.

For a request to change/save something, verify ALL:
1. The page/object identity matches the requested object.
2. An edit alone is not a saved change. There must be a submission after the edit.
3. The current page confirms the save or shows the saved result after submission.
4. A validation error means the save has not succeeded. Clicking Save is not enough.
A timeout on a redundant later click does not undo a previously confirmed save.
For read-only questions, check the proposed answer against the visible requested
field. For navigation, check the requested page/section is actually open.
Do not require a save for read-only or navigation tasks. Do not add extra goals.
If uncertain, reject with the specific missing observation, not a generic warning.

Example: goal "View order status", page "Status: Paid", proposed answer "Paid":
{"allow_finish": true, "reason": "Read-only status query; answer matches the visible status, no save needed."}
Example: goal "View order status", page "Status: Paid", proposed answer "Completed":
{"allow_finish": false, "reason": "Return the actual visible status, not a generic completion message."}
Example: requested update, current field has desired value, history only select_option:
{"allow_finish": false, "reason": "The field was edited but no save/submit followed; save the form."}
Example: history edited and clicked Save, correct record shows Changes saved:
{"allow_finish": true, "reason": "The requested edit was submitted and confirmed on the correct record."}
Example: history clicked Save, current form has Invalid numeric value:
{"allow_finish": false, "reason": "Validation blocked the save; correct the numeric input."}
Example: requested Item A, current page Item B shows Changes saved:
{"allow_finish": false, "reason": "The confirmation is for Item B; return to requested Item A."}
'''


class CompletionReviewBlocked(RuntimeError):
    pass


class CompletionCheckedBackend:
    def __init__(self,backend,protocol,*,max_corrections=2):
        self.backend=backend;self.protocol=protocol;self.model_name=backend.model_name
        self.max_corrections=max_corrections;self.events=[]

    def generate(self,messages,*,seed):
        # This experimental protocol has a JSON user body with all actor-visible data.
        context=json.loads(messages[-1]['content'])
        obs={'axtree_txt':context.get('observation','')}
        working=[dict(x) for x in messages]
        for attempt in range(self.max_corrections+1):
            proposal=self.backend.generate(working,seed=seed)
            try:action,_=self.protocol.parse(proposal.text,obs)
            except (ValueError,SyntaxError,TypeError):return proposal # normal parser feedback
            node=ast.parse(action,mode='eval').body
            if node.func.id!='send_msg_to_user':return proposal
            proposed_message=ast.literal_eval(node.args[0])
            review_messages=[{'role':'system','content':REVIEW_PROMPT},
                             {'role':'user','content':json.dumps({'actor_visible_context':context,'proposed_message':proposed_message},ensure_ascii=False)}]
            response=self.backend.generate(review_messages,seed=seed)
            try:
                review=parse_json_object(response.text)
                if type(review.get('allow_finish')) is not bool or not isinstance(review.get('reason'),str):raise ValueError('Malformed review')
            except (ValueError,TypeError):raise CompletionReviewBlocked('Local completion review returned invalid JSON; proposal not executed')
            self.events.append({'proposal':proposal.text,'review':review,'review_response':response.text,'correction_index':attempt})
            if review['allow_finish']:return proposal
            if attempt==self.max_corrections:raise CompletionReviewBlocked('Completion rejected after bounded corrections; no finish executed')
            working=messages+[{'role':'assistant','content':proposal.text},
                              {'role':'user','content':'Local completion review rejected this finish: '+review['reason']+'\nChoose the next action that addresses this issue using the current observation. Return one JSON action.'}]
        raise AssertionError('Unreachable')
