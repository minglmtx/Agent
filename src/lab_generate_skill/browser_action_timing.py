"""Shared BrowserGym deadlines and native associated-label click semantics.

Timeout configuration changes only waiting limits; the shared mapping also
handles a selected input's own covering label. No forced clicks or retries.
"""
import ast


def configure_action_timeout(action_set, milliseconds):
    if type(milliseconds) is not int or not 500<=milliseconds<=10000:
        raise ValueError('Action timeout must be 500..10000 ms')
    class Deadline(ast.NodeTransformer):
        count=0
        def visit_Call(self,node):
            self.generic_visit(node)
            if isinstance(node.func,ast.Attribute) and node.func.attr in ('click','dblclick','fill','clear','hover','select_option','check','uncheck','press','focus'):
                for kw in node.keywords:
                    if kw.arg=='timeout' and isinstance(kw.value,ast.Constant) and kw.value.value==500:
                        kw.value=ast.Constant(milliseconds);self.count+=1
            return node
    change=Deadline();tree=change.visit(ast.parse(action_set.python_includes))
    if change.count==0:raise RuntimeError('BrowserGym action API changed; no bounded action deadline found')
    action_set.python_includes=ast.unparse(ast.fix_missing_locations(tree))+'\n'
    return action_set


def make_browser_action_set():
    """One action surface for the structured actor and all website runners."""
    import os
    from browsergym.core.action.highlevel import HighLevelActionSet
    actions=HighLevelActionSet(subsets=['chat','bid','infeas','nav','tab'],strict=True,multiaction=False,retry_with_force=False)
    return configure_action_timeout(actions,int(os.environ.get('LAB_BROWSER_ACTION_TIMEOUT_MS','5000')))


def make_browser_action_mapping(action_set):
    """Same native associated-label click semantics on every website.

    No task reference, forced click, retry, or choice of a different control.
    Only a radio/checkbox covered by its own associated label is delegated to
    that label, which activates the exact input the actor already selected.
    """
    import os
    from .native_control_adapter import action_mapping
    return action_mapping(action_set,int(os.environ.get('LAB_BROWSER_ACTION_TIMEOUT_MS','5000')))
