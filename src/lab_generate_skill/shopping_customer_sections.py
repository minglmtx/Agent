"""Opt-in capability for initializing missing native customer-data sections.

Uses the website's own section registry and GET loader. No task parameters,
fixed product references, cookie fabrication or evaluator answers are involved.
"""
BOOTSTRAP = """options => new Promise(resolve => {
    let settled=false;
    const finish=value=>{if(!settled){settled=true;clearTimeout(timer);resolve(value)}};
    const timer=setTimeout(()=>finish({ready:false,reason:'native_section_deadline'}),30000);
    require(['Magento_Customer/js/customer-data','Magento_Customer/js/section-config','jquery'],(data,config,$)=>{
        data.getInitCustomerData().done(()=>{
          const waitedForNativeRequest=$.active>0;
          const bootstrap=()=>{
            if(settled)return;
            const names=config.filterClientSideSections(config.getSectionNames());
            const missing=names.filter(name=>{
                const value=data.get(name)();
                return !value || !Object.prototype.hasOwnProperty.call(value,'data_id');
            });
            const receipt={registered:names,missing_before:missing,waited_for_native_request:waitedForNativeRequest};
            const check=()=>{
                const absent=names.filter(name=>!Object.prototype.hasOwnProperty.call(data.get(name)()||{},'data_id'));
                finish({...receipt,missing_after:absent,initialized:true,ready:!options.require_complete_sections || absent.length===0});
            };
            if(!missing.length || !options.reload_missing){check();return;}
            data.reload(missing,false).done(check).fail(()=>finish({...receipt,ready:false,reason:'native_section_request_failed'}));
          };
          if($.active>0){$(document).one('ajaxStop',bootstrap)}else{bootstrap()}
        }).fail(()=>finish({ready:false,reason:'native_section_initialization_failed'}));
    },()=>finish({ready:false,reason:'native_section_module_failed'}));
})"""


class NativeSectionReadinessError(RuntimeError):
    """Public section names and readiness flags, without customer payloads."""
    def __init__(self, receipt):
        super().__init__('Native customer-data bootstrap incomplete')
        self.receipt = receipt if isinstance(receipt, dict) else {'ready': False, 'reason': 'invalid_receipt'}


def initialize_missing(page,*,reload_missing=True):
    page.wait_for_function("() => typeof require==='function'",timeout=15000)
    result=page.evaluate(BOOTSTRAP,{'reload_missing':reload_missing,'require_complete_sections':True})
    if not isinstance(result,dict)or result.get('ready')is not True:
        raise NativeSectionReadinessError(result)
    return result


def wait_initialized(page):
    """Wait for native initialization and its request, without repopulating data.

    Disposable messages can legitimately be cleared by the native component.
    Readiness does not promise nonempty sections or task-specific products.
    """
    page.wait_for_function("() => typeof require==='function'",timeout=15000)
    result=page.evaluate(BOOTSTRAP,{'reload_missing':False,'require_complete_sections':False})
    if not isinstance(result,dict) or result.get('ready') is not True:
        raise NativeSectionReadinessError(result)
    return result
