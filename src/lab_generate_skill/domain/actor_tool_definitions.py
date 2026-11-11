"""Frozen tool schema and program-side examples; examples grant no runtime rights."""

from typing import Any

CATALOG_SHA256: str = "5d94fda1857cbfc33d8d93a6bab817a392e36ded4c153ac3d72f85893f3e61ac"

TOOL_DEFINITIONS: dict[str, Any] = {
    "click": {
        "name": "click",
        "description": "Click the observed element once. Check the resulting "
        "observation; click is not proof of task success.",
        "kind": "browser_action",
        "inputSchema": {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
            "properties": {
                "bid": {
                    "type": "string",
                    "description": "Current observed "
                    "browser element bid; "
                    "not a region_id.",
                    "minLength": 1,
                },
                "button": {
                    "type": "string",
                    "enum": ["left", "middle", "right"],
                    "default": "left",
                },
                "modifiers": {
                    "type": "array",
                    "items": {
                        "type": "string",
                        "enum": ["Alt", "Control", "ControlOrMeta", "Meta", "Shift"],
                    },
                    "default": [],
                },
            },
            "required": ["bid"],
            "additionalProperties": False,
        },
        "argument_order": ["bid", "button", "modifiers"],
        "feedback": {
            "correction_template": "Use a current observed bid, not a "
            "region_id. Keyword arguments use =; "
            "button and modifiers must match the "
            "current enums.",
            "example_source": "wire.example_response",
            "selection": "Use only the clause matching the confirmed "
            "error; bind current public values and include "
            "the erroneous field in the corrected example. "
            "Never execute or silently apply the example.",
        },
        "wire": {
            "branch": "action",
            "encoding": "single_BrowserGym_function_string",
            "example_response": {
                "thought": "Format example only; use current " "task facts and IDs.",
                "action": "click('42')",
            },
        },
    },
    "dblclick": {
        "name": "dblclick",
        "description": "Double-click the observed element.",
        "kind": "browser_action",
        "inputSchema": {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
            "properties": {
                "bid": {
                    "type": "string",
                    "description": "Current observed "
                    "browser element "
                    "bid; not a "
                    "region_id.",
                    "minLength": 1,
                },
                "button": {
                    "type": "string",
                    "enum": ["left", "middle", "right"],
                    "default": "left",
                },
                "modifiers": {
                    "type": "array",
                    "items": {
                        "type": "string",
                        "enum": ["Alt", "Control", "ControlOrMeta", "Meta", "Shift"],
                    },
                    "default": [],
                },
            },
            "required": ["bid"],
            "additionalProperties": False,
        },
        "argument_order": ["bid", "button", "modifiers"],
        "feedback": {
            "correction_template": "Use one dblclick with a current "
            "observed bid. Keyword arguments use "
            "=; button and modifiers must match "
            "the current enums.",
            "example_source": "wire.example_response",
            "selection": "Use only the clause matching the confirmed "
            "error; bind current public values and include "
            "the erroneous field in the corrected example. "
            "Never execute or silently apply the example.",
        },
        "wire": {
            "branch": "action",
            "encoding": "single_BrowserGym_function_string",
            "example_response": {
                "thought": "Format example only; use " "current task facts and IDs.",
                "action": "dblclick('42')",
            },
        },
    },
    "fill": {
        "name": "fill",
        "description": "Replace an editable field’s contents; an empty value clears "
        "it.",
        "kind": "browser_action",
        "inputSchema": {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
            "properties": {
                "bid": {
                    "type": "string",
                    "description": "Current observed "
                    "browser element bid; "
                    "not a region_id.",
                    "minLength": 1,
                },
                "value": {
                    "type": "string",
                    "description": "Literal text; "
                    "preserve empty "
                    "string where the "
                    "operation permits "
                    "it.",
                },
                "enable_autocomplete_menu": {
                    "type": "boolean",
                    "default": False,
                    "description": "Use "
                    "the "
                    "native "
                    "autocomplete "
                    "typing "
                    "behavior.",
                },
            },
            "required": ["bid", "value"],
            "additionalProperties": False,
        },
        "argument_order": ["bid", "value", "enable_autocomplete_menu"],
        "feedback": {
            "correction_template": "Use an editable observed bid and a "
            "string value; an empty string clears "
            "it. enable_autocomplete_menu is a "
            "boolean.",
            "example_source": "wire.example_response",
            "selection": "Use only the clause matching the confirmed error; "
            "bind current public values and include the "
            "erroneous field in the corrected example. Never "
            "execute or silently apply the example.",
        },
        "wire": {
            "branch": "action",
            "encoding": "single_BrowserGym_function_string",
            "example_response": {
                "thought": "Format example only; use current " "task facts and IDs.",
                "action": "fill('42', 'example')",
            },
        },
    },
    "select_option": {
        "name": "select_option",
        "description": "Select existing option values or labels in an "
        "observed select control; an empty list deselects.",
        "kind": "browser_action",
        "inputSchema": {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
            "properties": {
                "bid": {
                    "type": "string",
                    "description": "Current "
                    "observed "
                    "browser "
                    "element bid; "
                    "not a "
                    "region_id.",
                    "minLength": 1,
                },
                "options": {
                    "oneOf": [
                        {"type": "string"},
                        {"type": "array", "items": {"type": "string"}},
                    ]
                },
            },
            "required": ["bid", "options"],
            "additionalProperties": False,
        },
        "argument_order": ["bid", "options"],
        "feedback": {
            "correction_template": "Use an observed select bid and "
            "an available option string or "
            "list of strings; preserve "
            "supported empty-list "
            "semantics.",
            "example_source": "wire.example_response",
            "selection": "Use only the clause matching the "
            "confirmed error; bind current public "
            "values and include the erroneous field "
            "in the corrected example. Never execute "
            "or silently apply the example.",
        },
        "wire": {
            "branch": "action",
            "encoding": "single_BrowserGym_function_string",
            "example_response": {
                "thought": "Format example only; use " "current task facts and " "IDs.",
                "action": "select_option('42', " "['blue'])",
            },
        },
    },
    "scroll": {
        "name": "scroll",
        "description": "Send a wheel event in pixels: positive x/right, positive "
        "y/down. Use the new observation afterward; this does not "
        "read a saved region.",
        "kind": "browser_action",
        "inputSchema": {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
            "properties": {
                "delta_x": {"type": "number"},
                "delta_y": {"type": "number"},
            },
            "required": ["delta_x", "delta_y"],
            "additionalProperties": False,
        },
        "argument_order": ["delta_x", "delta_y"],
        "feedback": {
            "correction_template": "Provide finite numeric delta_x and "
            "delta_y in pixels; right/down are "
            "positive. Use the new observation "
            "afterward.",
            "example_source": "wire.example_response",
            "selection": "Use only the clause matching the confirmed "
            "error; bind current public values and include "
            "the erroneous field in the corrected example. "
            "Never execute or silently apply the example.",
        },
        "wire": {
            "branch": "action",
            "encoding": "single_BrowserGym_function_string",
            "example_response": {
                "thought": "Format example only; use current " "task facts and IDs.",
                "action": "scroll(0, 400)",
            },
        },
    },
    "press": {
        "name": "press",
        "description": "Focus an observed element and press a key or key "
        "combination, e.g. Enter or Control+a.",
        "kind": "browser_action",
        "inputSchema": {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
            "properties": {
                "bid": {
                    "type": "string",
                    "description": "Current observed "
                    "browser element bid; "
                    "not a region_id.",
                    "minLength": 1,
                },
                "key_comb": {
                    "type": "string",
                    "description": "Native key or " "modifier+key " "combination.",
                    "minLength": 1,
                },
            },
            "required": ["bid", "key_comb"],
            "additionalProperties": False,
        },
        "argument_order": ["bid", "key_comb"],
        "feedback": {
            "correction_template": "Use a current observed bid and a "
            "key_comb string supported by the "
            "browser, such as Enter.",
            "example_source": "wire.example_response",
            "selection": "Use only the clause matching the confirmed "
            "error; bind current public values and include "
            "the erroneous field in the corrected example. "
            "Never execute or silently apply the example.",
        },
        "wire": {
            "branch": "action",
            "encoding": "single_BrowserGym_function_string",
            "example_response": {
                "thought": "Format example only; use current " "task facts and IDs.",
                "action": "press('42', 'Enter')",
            },
        },
    },
    "hover": {
        "name": "hover",
        "description": "Move the pointer over an observed element; inspect the next "
        "observation for revealed content.",
        "kind": "browser_action",
        "inputSchema": {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
            "properties": {
                "bid": {
                    "type": "string",
                    "description": "Current observed "
                    "browser element bid; "
                    "not a region_id.",
                    "minLength": 1,
                }
            },
            "required": ["bid"],
            "additionalProperties": False,
        },
        "argument_order": ["bid"],
        "feedback": {
            "correction_template": "Provide only the current observed bid; "
            "use a new observation to establish any "
            "revealed content.",
            "example_source": "wire.example_response",
            "selection": "Use only the clause matching the confirmed "
            "error; bind current public values and include "
            "the erroneous field in the corrected example. "
            "Never execute or silently apply the example.",
        },
        "wire": {
            "branch": "action",
            "encoding": "single_BrowserGym_function_string",
            "example_response": {
                "thought": "Format example only; use current " "task facts and IDs.",
                "action": "hover('42')",
            },
        },
    },
    "focus": {
        "name": "focus",
        "description": "Focus an observed element without implying task completion.",
        "kind": "browser_action",
        "inputSchema": {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
            "properties": {
                "bid": {
                    "type": "string",
                    "description": "Current observed "
                    "browser element bid; "
                    "not a region_id.",
                    "minLength": 1,
                }
            },
            "required": ["bid"],
            "additionalProperties": False,
        },
        "argument_order": ["bid"],
        "feedback": {
            "correction_template": "Provide only the current observed bid.",
            "example_source": "wire.example_response",
            "selection": "Use only the clause matching the confirmed "
            "error; bind current public values and include "
            "the erroneous field in the corrected example. "
            "Never execute or silently apply the example.",
        },
        "wire": {
            "branch": "action",
            "encoding": "single_BrowserGym_function_string",
            "example_response": {
                "thought": "Format example only; use current " "task facts and IDs.",
                "action": "focus('42')",
            },
        },
    },
    "clear": {
        "name": "clear",
        "description": "Clear an observed editable field.",
        "kind": "browser_action",
        "inputSchema": {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
            "properties": {
                "bid": {
                    "type": "string",
                    "description": "Current observed "
                    "browser element bid; "
                    "not a region_id.",
                    "minLength": 1,
                }
            },
            "required": ["bid"],
            "additionalProperties": False,
        },
        "argument_order": ["bid"],
        "feedback": {
            "correction_template": "Provide only an observed editable bid; "
            "this operation clears its content.",
            "example_source": "wire.example_response",
            "selection": "Use only the clause matching the confirmed "
            "error; bind current public values and include "
            "the erroneous field in the corrected example. "
            "Never execute or silently apply the example.",
        },
        "wire": {
            "branch": "action",
            "encoding": "single_BrowserGym_function_string",
            "example_response": {
                "thought": "Format example only; use current " "task facts and IDs.",
                "action": "clear('42')",
            },
        },
    },
    "drag_and_drop": {
        "name": "drag_and_drop",
        "description": "Drag one observed element onto another observed " "element.",
        "kind": "browser_action",
        "inputSchema": {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
            "properties": {
                "from_bid": {
                    "type": "string",
                    "description": "Current "
                    "observed "
                    "browser "
                    "element "
                    "bid; "
                    "not a "
                    "region_id.",
                    "minLength": 1,
                },
                "to_bid": {
                    "type": "string",
                    "description": "Current "
                    "observed "
                    "browser "
                    "element "
                    "bid; not "
                    "a "
                    "region_id.",
                    "minLength": 1,
                },
            },
            "required": ["from_bid", "to_bid"],
            "additionalProperties": False,
        },
        "argument_order": ["from_bid", "to_bid"],
        "feedback": {
            "correction_template": "Provide distinct argument "
            "fields from_bid and to_bid, "
            "both bound to current observed "
            "elements.",
            "example_source": "wire.example_response",
            "selection": "Use only the clause matching the "
            "confirmed error; bind current public "
            "values and include the erroneous field "
            "in the corrected example. Never execute "
            "or silently apply the example.",
        },
        "wire": {
            "branch": "action",
            "encoding": "single_BrowserGym_function_string",
            "example_response": {
                "thought": "Format example only; use " "current task facts and " "IDs.",
                "action": "drag_and_drop('42', " "'43')",
            },
        },
    },
    "upload_file": {
        "name": "upload_file",
        "description": "Open the observed upload control and choose permitted "
        "attempt-local files; an empty list clears selection.",
        "kind": "browser_action",
        "inputSchema": {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
            "properties": {
                "bid": {
                    "type": "string",
                    "description": "Current "
                    "observed "
                    "browser "
                    "element bid; "
                    "not a "
                    "region_id.",
                    "minLength": 1,
                },
                "file": {
                    "oneOf": [
                        {
                            "type": "string",
                            "description": "A "
                            "file "
                            "in "
                            "this "
                            "attempt’s "
                            "allowed "
                            "local "
                            "files; "
                            "no "
                            "arbitrary "
                            "filesystem "
                            "access.",
                            "minLength": 1,
                        },
                        {
                            "type": "array",
                            "items": {
                                "type": "string",
                                "description": "A "
                                "file "
                                "in "
                                "this "
                                "attempt’s "
                                "allowed "
                                "local "
                                "files; "
                                "no "
                                "arbitrary "
                                "filesystem "
                                "access.",
                                "minLength": 1,
                            },
                        },
                    ]
                },
            },
            "required": ["bid", "file"],
            "additionalProperties": False,
        },
        "argument_order": ["bid", "file"],
        "feedback": {
            "correction_template": "Use the keyword file and only "
            "permitted files from this "
            "instance; never invent a path. "
            "An empty list clears the "
            "selection.",
            "example_source": "wire.example_response",
            "selection": "Use only the clause matching the confirmed "
            "error; bind current public values and "
            "include the erroneous field in the "
            "corrected example. Never execute or "
            "silently apply the example.",
        },
        "wire": {
            "branch": "action",
            "encoding": "single_BrowserGym_function_string",
            "example_response": {
                "thought": "Format example only; use " "current task facts and IDs.",
                "action": "upload_file('42', [])",
            },
        },
    },
    "goto": {
        "name": "goto",
        "description": "Navigate to a URL allowed by the current task and network "
        "policy.",
        "kind": "browser_action",
        "inputSchema": {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "Observed or otherwise " "task-authorized URL.",
                    "minLength": 1,
                }
            },
            "required": ["url"],
            "additionalProperties": False,
        },
        "argument_order": ["url"],
        "feedback": {
            "correction_template": "Provide a URL string allowed for this " "task.",
            "example_source": "wire.example_response",
            "selection": "Use only the clause matching the confirmed error; "
            "bind current public values and include the "
            "erroneous field in the corrected example. Never "
            "execute or silently apply the example.",
        },
        "wire": {
            "branch": "action",
            "encoding": "single_BrowserGym_function_string",
            "example_response": {
                "thought": "Format example only; use current " "task facts and IDs.",
                "action": "goto('https://example.invalid/')",
            },
        },
    },
    "go_back": {
        "name": "go_back",
        "description": "Navigate back in the current tab’s history.",
        "kind": "browser_action",
        "inputSchema": {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
            "properties": {},
            "required": [],
            "additionalProperties": False,
        },
        "argument_order": [],
        "feedback": {
            "correction_template": "Call go_back() without arguments.",
            "example_source": "wire.example_response",
            "selection": "Use only the clause matching the confirmed "
            "error; bind current public values and include "
            "the erroneous field in the corrected example. "
            "Never execute or silently apply the example.",
        },
        "wire": {
            "branch": "action",
            "encoding": "single_BrowserGym_function_string",
            "example_response": {
                "thought": "Format example only; use " "current task facts and IDs.",
                "action": "go_back()",
            },
        },
    },
    "go_forward": {
        "name": "go_forward",
        "description": "Navigate forward in the current tab’s history.",
        "kind": "browser_action",
        "inputSchema": {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
            "properties": {},
            "required": [],
            "additionalProperties": False,
        },
        "argument_order": [],
        "feedback": {
            "correction_template": "Call go_forward() without " "arguments.",
            "example_source": "wire.example_response",
            "selection": "Use only the clause matching the confirmed "
            "error; bind current public values and "
            "include the erroneous field in the "
            "corrected example. Never execute or "
            "silently apply the example.",
        },
        "wire": {
            "branch": "action",
            "encoding": "single_BrowserGym_function_string",
            "example_response": {
                "thought": "Format example only; use " "current task facts and IDs.",
                "action": "go_forward()",
            },
        },
    },
    "new_tab": {
        "name": "new_tab",
        "description": "Open a new tab and make it active.",
        "kind": "browser_action",
        "inputSchema": {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
            "properties": {},
            "required": [],
            "additionalProperties": False,
        },
        "argument_order": [],
        "feedback": {
            "correction_template": "Call new_tab() without arguments.",
            "example_source": "wire.example_response",
            "selection": "Use only the clause matching the confirmed "
            "error; bind current public values and include "
            "the erroneous field in the corrected example. "
            "Never execute or silently apply the example.",
        },
        "wire": {
            "branch": "action",
            "encoding": "single_BrowserGym_function_string",
            "example_response": {
                "thought": "Format example only; use " "current task facts and IDs.",
                "action": "new_tab()",
            },
        },
    },
    "tab_focus": {
        "name": "tab_focus",
        "description": "Activate an existing tab by its zero-based index.",
        "kind": "browser_action",
        "inputSchema": {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
            "properties": {
                "index": {
                    "type": "integer",
                    "minimum": 0,
                    "description": "Index in the "
                    "current "
                    "observation’s "
                    "tab list.",
                }
            },
            "required": ["index"],
            "additionalProperties": False,
        },
        "argument_order": ["index"],
        "feedback": {
            "correction_template": "Use a strict integer index from 0 "
            "to the current tab count minus 1.",
            "example_source": "wire.example_response",
            "selection": "Use only the clause matching the confirmed "
            "error; bind current public values and "
            "include the erroneous field in the corrected "
            "example. Never execute or silently apply the "
            "example.",
        },
        "wire": {
            "branch": "action",
            "encoding": "single_BrowserGym_function_string",
            "example_response": {
                "thought": "Format example only; use " "current task facts and IDs.",
                "action": "tab_focus(0)",
            },
        },
    },
    "tab_close": {
        "name": "tab_close",
        "description": "Close the current tab.",
        "kind": "browser_action",
        "inputSchema": {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
            "properties": {},
            "required": [],
            "additionalProperties": False,
        },
        "argument_order": [],
        "feedback": {
            "correction_template": "Call tab_close() without "
            "arguments; it closes the current "
            "tab.",
            "example_source": "wire.example_response",
            "selection": "Use only the clause matching the confirmed "
            "error; bind current public values and "
            "include the erroneous field in the corrected "
            "example. Never execute or silently apply the "
            "example.",
        },
        "wire": {
            "branch": "action",
            "encoding": "single_BrowserGym_function_string",
            "example_response": {
                "thought": "Format example only; use " "current task facts and IDs.",
                "action": "tab_close()",
            },
        },
    },
    "noop": {
        "name": "noop",
        "description": "Wait only for an expected pending page change; do not use "
        "this to finish a task.",
        "kind": "browser_action",
        "inputSchema": {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
            "properties": {
                "wait_ms": {
                    "type": "number",
                    "minimum": 0,
                    "default": 1000,
                    "description": "Milliseconds; "
                    "must fit the "
                    "remaining action "
                    "budget.",
                }
            },
            "required": [],
            "additionalProperties": False,
        },
        "argument_order": ["wait_ms"],
        "feedback": {
            "correction_template": "Use nonnegative finite wait_ms within "
            "the original remaining action budget, "
            "only for an expected pending change.",
            "example_source": "wire.example_response",
            "selection": "Use only the clause matching the confirmed error; "
            "bind current public values and include the "
            "erroneous field in the corrected example. Never "
            "execute or silently apply the example.",
        },
        "wire": {
            "branch": "action",
            "encoding": "single_BrowserGym_function_string",
            "example_response": {
                "thought": "Format example only; use current " "task facts and IDs.",
                "action": "noop()",
            },
        },
    },
    "send_msg_to_user": {
        "name": "send_msg_to_user",
        "description": "Finish with an answer supported by observed "
        "facts; this call is not the independent business "
        "verdict.",
        "kind": "browser_action",
        "inputSchema": {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": "Answer "
                    "or "
                    "completion "
                    "message "
                    "supported "
                    "by "
                    "actual "
                    "observations.",
                }
            },
            "required": ["text"],
            "additionalProperties": False,
        },
        "argument_order": ["text"],
        "feedback": {
            "correction_template": "Provide a text string "
            "supported by actual "
            "observations; a valid call "
            "does not establish business "
            "success.",
            "example_source": "wire.example_response",
            "selection": "Use only the clause matching the "
            "confirmed error; bind current public "
            "values and include the erroneous "
            "field in the corrected example. Never "
            "execute or silently apply the "
            "example.",
        },
        "wire": {
            "branch": "action",
            "encoding": "single_BrowserGym_function_string",
            "example_response": {
                "thought": "Format example only; " "use current task facts " "and IDs.",
                "action": "send_msg_to_user('Report "
                "only verified "
                "observations.')",
            },
        },
    },
    "report_infeasible": {
        "name": "report_infeasible",
        "description": "Finish by explaining a verified inability to "
        "complete the goal; not merely missing content "
        "in a partial view.",
        "kind": "browser_action",
        "inputSchema": {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
            "properties": {
                "reason": {
                    "type": "string",
                    "description": "Observed "
                    "limitation; "
                    "do "
                    "not "
                    "infer "
                    "absence "
                    "from "
                    "omitted "
                    "or "
                    "unloaded "
                    "content.",
                }
            },
            "required": ["reason"],
            "additionalProperties": False,
        },
        "argument_order": ["reason"],
        "feedback": {
            "correction_template": "Provide a reason string "
            "describing a verified "
            "limitation; omitted "
            "content alone does not "
            "prove infeasibility.",
            "example_source": "wire.example_response",
            "selection": "Use only the clause matching the "
            "confirmed error; bind current public "
            "values and include the erroneous "
            "field in the corrected example. "
            "Never execute or silently apply the "
            "example.",
        },
        "wire": {
            "branch": "action",
            "encoding": "single_BrowserGym_function_string",
            "example_response": {
                "thought": "Format example only; " "use current task " "facts and IDs.",
                "action": "report_infeasible('Describe "
                "the verified "
                "limitation.')",
            },
        },
    },
    "list_regions": {
        "name": "list_regions",
        "description": "List captured structural regions, or direct children "
        "of a known region. This is not a browser click and "
        "does not discover unloaded pages.",
        "kind": "observation_read",
        "inputSchema": {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
            "properties": {
                "schema_version": {
                    "type": "string",
                    "const": "observation-read-choice/1",
                    "default": "observation-read-choice/1",
                },
                "snapshot_sha256": {
                    "type": "string",
                    "pattern": "^[0-9a-f]{64}$",
                    "description": "Exact "
                    "observation "
                    "hash "
                    "in "
                    "the "
                    "current "
                    "prompt. "
                    "Bound "
                    "to "
                    "const "
                    "before "
                    "publication.",
                },
                "output_tokens": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 61440,
                    "description": "Maximum "
                    "read "
                    "body "
                    "tokens, "
                    "including "
                    "required "
                    "context. "
                    "Effective "
                    "maximum "
                    "comes "
                    "from "
                    "the "
                    "frozen "
                    "policy.",
                },
                "continuation": {
                    "anyOf": [
                        {
                            "type": "string",
                            "minLength": 1,
                            "maxLength": 256,
                            "pattern": "^[A-Za-z0-9][A-Za-z0-9_.:-]*$",
                        },
                        {"type": "null"},
                    ],
                    "default": None,
                    "description": "Original "
                    "continuation "
                    "from "
                    "the "
                    "same "
                    "snapshot "
                    "and "
                    "identical "
                    "request "
                    "parameters; "
                    "null "
                    "starts "
                    "a "
                    "new "
                    "read.",
                },
                "tool": {"type": "string", "const": "list_regions"},
                "parent_region_id": {
                    "anyOf": [
                        {
                            "type": "string",
                            "minLength": 1,
                            "maxLength": 256,
                            "pattern": "^ax-line-(0|[1-9][0-9]*)$",
                            "description": "Copy "
                            "a "
                            "region_id "
                            "from "
                            "the "
                            "current "
                            "region "
                            "directory/search. "
                            "Not "
                            "a "
                            "browser "
                            "bid; "
                            "never "
                            "construct "
                            "it "
                            "from "
                            "a "
                            "label.",
                        },
                        {"type": "null"},
                    ],
                    "default": None,
                },
            },
            "required": ["tool", "snapshot_sha256", "output_tokens"],
            "additionalProperties": False,
        },
        "feedback": {
            "correction_template": "Use a read object bound to the "
            "current snapshot; "
            "parent_region_id must be null "
            "or a current directory region "
            "ID.",
            "example_source": "wire.example_response",
            "selection": "Use only the clause matching the "
            "confirmed error; bind current public "
            "values and include the erroneous field in "
            "the corrected example. Never execute or "
            "silently apply the example.",
        },
        "wire": {
            "branch": "read",
            "encoding": "observation-read-choice/1_object",
            "example_response": {
                "thought": "Format example only; this "
                "read has not been "
                "executed.",
                "read": {
                    "schema_version": "observation-read-choice/1",
                    "tool": "list_regions",
                    "snapshot_sha256": "0000000000000000000000000000000000000000000000000000000000000000",
                    "output_tokens": 1500,
                    "continuation": None,
                    "parent_region_id": None,
                },
            },
        },
    },
    "read_region": {
        "name": "read_region",
        "description": "Read captured but unshown content by directory region "
        "IDs. Do not reread sufficient displayed content. Does "
        "not expand menus, scroll or load pages.",
        "kind": "observation_read",
        "inputSchema": {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
            "properties": {
                "schema_version": {
                    "type": "string",
                    "const": "observation-read-choice/1",
                    "default": "observation-read-choice/1",
                },
                "snapshot_sha256": {
                    "type": "string",
                    "pattern": "^[0-9a-f]{64}$",
                    "description": "Exact "
                    "observation "
                    "hash "
                    "in "
                    "the "
                    "current "
                    "prompt. "
                    "Bound "
                    "to "
                    "const "
                    "before "
                    "publication.",
                },
                "output_tokens": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 61440,
                    "description": "Maximum "
                    "read "
                    "body "
                    "tokens, "
                    "including "
                    "required "
                    "context. "
                    "Effective "
                    "maximum "
                    "comes "
                    "from "
                    "the "
                    "frozen "
                    "policy.",
                },
                "continuation": {
                    "anyOf": [
                        {
                            "type": "string",
                            "minLength": 1,
                            "maxLength": 256,
                            "pattern": "^[A-Za-z0-9][A-Za-z0-9_.:-]*$",
                        },
                        {"type": "null"},
                    ],
                    "default": None,
                    "description": "Original "
                    "continuation "
                    "from "
                    "the "
                    "same "
                    "snapshot "
                    "and "
                    "identical "
                    "request "
                    "parameters; "
                    "null "
                    "starts "
                    "a new "
                    "read.",
                },
                "tool": {"type": "string", "const": "read_region"},
                "ranges": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": 16,
                    "items": {
                        "oneOf": [
                            {
                                "type": "object",
                                "properties": {
                                    "region_id": {
                                        "type": "string",
                                        "minLength": 1,
                                        "maxLength": 256,
                                        "pattern": "^ax-line-(0|[1-9][0-9]*)$",
                                        "description": "Copy "
                                        "a "
                                        "region_id "
                                        "from "
                                        "the "
                                        "current "
                                        "region "
                                        "directory/search. "
                                        "Not "
                                        "a "
                                        "browser "
                                        "bid; "
                                        "never "
                                        "construct "
                                        "it "
                                        "from "
                                        "a "
                                        "label.",
                                    },
                                    "unit": {"const": "whole_region"},
                                    "start": {"type": "null", "default": None},
                                    "end": {"type": "null", "default": None},
                                },
                                "required": ["region_id", "unit"],
                                "additionalProperties": False,
                            },
                            {
                                "type": "object",
                                "properties": {
                                    "region_id": {
                                        "type": "string",
                                        "minLength": 1,
                                        "maxLength": 256,
                                        "pattern": "^ax-line-(0|[1-9][0-9]*)$",
                                        "description": "Copy "
                                        "a "
                                        "region_id "
                                        "from "
                                        "the "
                                        "current "
                                        "region "
                                        "directory/search. "
                                        "Not "
                                        "a "
                                        "browser "
                                        "bid; "
                                        "never "
                                        "construct "
                                        "it "
                                        "from "
                                        "a "
                                        "label.",
                                    },
                                    "unit": {"enum": ["data_rows", "codepoints"]},
                                    "start": {
                                        "type": "integer",
                                        "minimum": 0,
                                        "description": "Zero-based "
                                        "inclusive "
                                        "start; "
                                        "data_rows "
                                        "excludes "
                                        "table "
                                        "header "
                                        "rows.",
                                    },
                                    "end": {
                                        "type": "integer",
                                        "minimum": 1,
                                        "description": "Exclusive "
                                        "end. "
                                        "Must "
                                        "exceed "
                                        "start "
                                        "and "
                                        "stay "
                                        "within "
                                        "the "
                                        "captured "
                                        "region.",
                                    },
                                },
                                "required": ["region_id", "unit", "start", "end"],
                                "additionalProperties": False,
                            },
                        ]
                    },
                    "description": "Independent "
                    "requested "
                    "ranges. "
                    "Effective "
                    "maxItems "
                    "comes from "
                    "the frozen "
                    "read "
                    "policy, not "
                    "this "
                    "absolute "
                    "ceiling.",
                },
            },
            "required": ["tool", "snapshot_sha256", "output_tokens", "ranges"],
            "additionalProperties": False,
        },
        "feedback": {
            "correction_template": "Use current directory region IDs "
            "and the effective range-count, "
            "unit and half-open bounds; use a "
            "read object, not an action "
            "string.",
            "example_source": "wire.example_response",
            "selection": "Use only the clause matching the confirmed "
            "error; bind current public values and "
            "include the erroneous field in the "
            "corrected example. Never execute or "
            "silently apply the example.",
        },
        "wire": {
            "branch": "read",
            "encoding": "observation-read-choice/1_object",
            "example_response": {
                "thought": "Format example only; this " "read has not been executed.",
                "read": {
                    "schema_version": "observation-read-choice/1",
                    "tool": "read_region",
                    "snapshot_sha256": "0000000000000000000000000000000000000000000000000000000000000000",
                    "output_tokens": 1500,
                    "continuation": None,
                    "ranges": [{"region_id": "ax-line-0", "unit": "whole_region"}],
                },
            },
        },
    },
    "search_regions": {
        "name": "search_regions",
        "description": "Search literal Unicode-casefold substrings within "
        "captured text; no regex, fuzzy, semantic or "
        "website-wide search. Multiple words form one "
        "literal phrase. Hits retain their enclosing "
        "context/row; inspect coverage and continuation.",
        "kind": "observation_read",
        "inputSchema": {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
            "properties": {
                "schema_version": {
                    "type": "string",
                    "const": "observation-read-choice/1",
                    "default": "observation-read-choice/1",
                },
                "snapshot_sha256": {
                    "type": "string",
                    "pattern": "^[0-9a-f]{64}$",
                    "description": "Exact "
                    "observation "
                    "hash "
                    "in "
                    "the "
                    "current "
                    "prompt. "
                    "Bound "
                    "to "
                    "const "
                    "before "
                    "publication.",
                },
                "output_tokens": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 61440,
                    "description": "Maximum "
                    "read "
                    "body "
                    "tokens, "
                    "including "
                    "required "
                    "context. "
                    "Effective "
                    "maximum "
                    "comes "
                    "from "
                    "the "
                    "frozen "
                    "policy.",
                },
                "continuation": {
                    "anyOf": [
                        {
                            "type": "string",
                            "minLength": 1,
                            "maxLength": 256,
                            "pattern": "^[A-Za-z0-9][A-Za-z0-9_.:-]*$",
                        },
                        {"type": "null"},
                    ],
                    "default": None,
                    "description": "Original "
                    "continuation "
                    "from "
                    "the "
                    "same "
                    "snapshot "
                    "and "
                    "identical "
                    "request "
                    "parameters; "
                    "null "
                    "starts "
                    "a "
                    "new "
                    "read.",
                },
                "tool": {"type": "string", "const": "search_regions"},
                "query": {
                    "type": "string",
                    "description": "Nonempty "
                    "literal "
                    "substring, "
                    "not a "
                    "regular "
                    "expression.",
                    "minLength": 1,
                    "maxLength": 256,
                },
                "mode": {
                    "type": "string",
                    "const": "unicode_casefold_literal/1",
                    "default": "unicode_casefold_literal/1",
                },
                "region_ids": {
                    "type": "array",
                    "items": {
                        "type": "string",
                        "minLength": 1,
                        "maxLength": 256,
                        "pattern": "^ax-line-(0|[1-9][0-9]*)$",
                        "description": "Copy "
                        "a "
                        "region_id "
                        "from "
                        "the "
                        "current "
                        "region "
                        "directory/search. "
                        "Not "
                        "a "
                        "browser "
                        "bid; "
                        "never "
                        "construct "
                        "it "
                        "from "
                        "a "
                        "label.",
                    },
                    "maxItems": 128,
                    "uniqueItems": True,
                    "description": "Current "
                    "region "
                    "IDs; "
                    "[] "
                    "searches "
                    "this "
                    "captured "
                    "snapshot, "
                    "not "
                    "unloaded "
                    "pages.",
                },
            },
            "required": [
                "tool",
                "snapshot_sha256",
                "output_tokens",
                "query",
                "region_ids",
            ],
            "additionalProperties": False,
        },
        "feedback": {
            "correction_template": "Use a nonempty literal query "
            "and current region IDs; [] "
            "searches only the captured "
            "snapshot. Put the tool in a "
            "read object.",
            "example_source": "wire.example_response",
            "selection": "Use only the clause matching the "
            "confirmed error; bind current public "
            "values and include the erroneous field "
            "in the corrected example. Never execute "
            "or silently apply the example.",
        },
        "wire": {
            "branch": "read",
            "encoding": "observation-read-choice/1_object",
            "example_response": {
                "thought": "Format example only; "
                "this read has not been "
                "executed.",
                "read": {
                    "schema_version": "observation-read-choice/1",
                    "tool": "search_regions",
                    "snapshot_sha256": "0000000000000000000000000000000000000000000000000000000000000000",
                    "output_tokens": 1500,
                    "continuation": None,
                    "query": "example text",
                    "mode": "unicode_casefold_literal/1",
                    "region_ids": [],
                },
            },
        },
    },
}

RESPONSE_ENVELOPE: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "oneOf": [
        {
            "type": "object",
            "properties": {
                "thought": {"type": "string"},
                "action": {"type": "string", "minLength": 1},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        {
            "type": "object",
            "properties": {"thought": {"type": "string"}, "read": {}},
            "required": ["read"],
            "additionalProperties": False,
        },
    ],
}

REJECTION_FEEDBACK_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "properties": {
        "status": {"const": "proposal_rejected"},
        "executed": {"const": False},
        "tool": {"type": ["string", "null"]},
        "code": {
            "enum": [
                "INVALID_JSON",
                "INVALID_RESPONSE_SHAPE",
                "WRONG_TOOL_BRANCH",
                "UNKNOWN_TOOL",
                "INVALID_ARGUMENTS",
                "RANGE_COUNT_EXCEEDED",
                "OUTPUT_BUDGET_EXCEEDED",
                "STALE_SNAPSHOT",
                "UNKNOWN_REGION",
                "RANGE_OUT_OF_BOUNDS",
                "INVALID_CONTINUATION",
                "READ_QUOTA_EXHAUSTED",
                "REPEATED_INVALID_PROPOSAL",
                "INVALID_PROPOSAL_LIMIT",
            ]
        },
        "message": {"type": "string"},
        "field": {"type": ["string", "null"]},
        "actual": {},
        "allowed": {},
        "next_action": {"type": "string"},
        "can_correct": {"type": "boolean"},
        "consecutive_invalid": {"type": "integer", "minimum": 0},
        "repeated_invalid": {"type": "integer", "minimum": 0},
    },
    "required": [
        "status",
        "executed",
        "tool",
        "code",
        "message",
        "field",
        "actual",
        "allowed",
        "next_action",
        "can_correct",
        "consecutive_invalid",
        "repeated_invalid",
    ],
    "additionalProperties": False,
}
