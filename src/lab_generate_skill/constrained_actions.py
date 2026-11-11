"""Optional generation-time JSON/action-name constraints, with no task answers."""
from .actor_protocol import SIGNATURES
from .answer_values import bounded_answer_schema


def action_output_schema(*, nullable_fields=(), print_to_pdf=False, artifact_actions=()):
    from .local_artifact_actions import TOOL_SCHEMAS
    if not isinstance(artifact_actions, (tuple, list)) or any(
            not isinstance(name, str) or name not in TOOL_SCHEMAS for name in artifact_actions):
        raise ValueError('Only installed native artifact action names may extend decoding')
    answer, definitions = (bounded_answer_schema(nullable_fields=nullable_fields)
                           if nullable_fields else bounded_answer_schema())
    return {
        '$defs': definitions,
        'type':'object',
        'properties':{
            'thought':{'type':'string','maxLength':240},
            'action':{'type':'string','enum':sorted((set(SIGNATURES)-{'send_msg_to_user', 'print_page'})|{'finish'}|({'print_page'} if print_to_pdf is True else set())|set(artifact_actions))},
            'args':{'type':'array','items':{'anyOf':[{'type':'string'},{'type':'number'},{'type':'array','items':{'type':'string'}}]}},
            'answer':answer,
        },
        'required':['action'], 'additionalProperties':False,
    }


def make_action_parser(tokenizer_data, *, nullable_fields=(), print_to_pdf=False, artifact_actions=()):
    """Set the tokenizer alphabet before JSON string states cache it.

    Setting config only inside TokenEnforcer is too late for minLength string
    states: a non-ASCII first character can then empty the parse stack and
    allow EOS inside an unfinished answer.
    """
    from lmformatenforcer import JsonSchemaParser
    from lmformatenforcer.characterlevelparser import CharacterLevelParserConfig
    config=CharacterLevelParserConfig(alphabet=tokenizer_data.tokenizer_alphabet)
    return JsonSchemaParser(action_output_schema(nullable_fields=nullable_fields, print_to_pdf=print_to_pdf, artifact_actions=artifact_actions),config=config)


def make_action_enforcer(tokenizer_data, *, nullable_fields=(), print_to_pdf=False, artifact_actions=()):
    """Preserve the fast text cache, but explore legal JSON escape prefixes.

    The dependency's free-text shortcut explores only quote-prefixed tokens.
    Its cache omits incomplete escape tokens such as ``\\u``. Such a token is
    valid when followed by four hex digits, and must be checked by the parser.
    """
    from lmformatenforcer.tokenenforcer import TokenEnforcer

    class ActionTokenEnforcer(TokenEnforcer):
        def _collect_allowed_tokens(self, parser, tree_node, allowed_tokens, shortcut_key):
            super()._collect_allowed_tokens(parser, tree_node, allowed_tokens, shortcut_key)
            if (isinstance(shortcut_key, tuple) and shortcut_key[0] == 'json_freetext'
                    and '\\' in tree_node.children and '\\' in parser.get_allowed_characters()):
                self._collect_allowed_tokens(parser.add_character('\\'),
                    tree_node.children['\\'], allowed_tokens, None)

    return ActionTokenEnforcer(tokenizer_data,
        make_action_parser(tokenizer_data, nullable_fields=nullable_fields, print_to_pdf=print_to_pdf, artifact_actions=artifact_actions))


def make_action_prefix(backend):
    from lmformatenforcer.integrations.transformers import build_token_enforcer_tokenizer_data, TransformersPrefixAllowedTokensFn
    data=getattr(backend,'_action_tokenizer_data',None)
    if data is None:
        data=build_token_enforcer_tokenizer_data(backend._tokenizer)
        backend._action_tokenizer_data=data
    return TransformersPrefixAllowedTokensFn(make_action_enforcer(data,
        nullable_fields=getattr(backend, '_action_nullable_answer_fields', ()),
        print_to_pdf=getattr(backend, '_action_print_to_pdf', False),
        artifact_actions=getattr(backend, '_native_artifact_action_names', ())))
