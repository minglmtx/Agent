"""Filter redundant native data-child UI refreshes; never suppress map events."""
import hashlib
VERSION='native-mapdata-child-ui-refresh-v2'
PINNED={'index.js': '10dd34fa707fa45b795c07c1070bd38c368e4c37e63825ca1b5ec93101e74424', 'leaflet.share.js': '69e60af41fd672f84f919d72255465c46711cad2f1778b80cca8be3e50e7beba', 'leaflet.layers.js': '54608669c8498eec2f834a92058ceb869f78b51b02249fd52161d00123b94228'}
GUARD="""      if (event && (event.type === "layeradd" || event.type === "layerremove") &&
          event.layer && (!event.layer.options || (!event.layer.options.code && !event.layer.options.keyid)) &&
          map.dataLayer.hasLayer(event.layer)) return;
"""
def patch_source(name, source):
    if name not in PINNED or hashlib.sha256(source.encode()).hexdigest()!=PINNED[name]:
        raise ValueError('Exact reviewed native UI source required')
    if name=='index.js':
        before='  map.on("moveend layeradd layerremove", function () {\n'
        after='  map.on("moveend layeradd layerremove", function (event) {\n'+GUARD
        count=1
    elif name=='leaflet.share.js':
        before='    function update() {\n'
        after='    function update(event) {\n'+GUARD
        count=1
    else:
        before='map.on("layeradd layerremove", function () {\n'
        after='map.on("layeradd layerremove", function (event) {\n'+GUARD
        count=2
    if source.count(before)!=count:raise ValueError('Native callback boundary changed')
    return source.replace(before,after)
def patch_index(source):return patch_source('index.js',source)


def location_listener(source):
    start=source.index('  map.on("moveend layeradd layerremove",')
    end=source.index('\n  });',start)+len('\n  });')
    return source[start:end]
