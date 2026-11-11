"""Explicit local short-route extension. No mutable token database or target IDs.

The public route's mode and endpoints are packed in a fixed bounded token, then
native /go retains its viewport decoding and redirects to native directions.
Coordinates retain six decimals; no evaluator reference enters the token.
"""
import base64,math,re,struct

MODES=('car','bike','foot')


def encode(pair,mode):
    if mode not in MODES or not isinstance(pair,list)or len(pair)!=2:raise ValueError('Public native route required')
    values=[]
    for point in pair:
        if not isinstance(point,list)or len(point)!=2:raise ValueError('Latitude/longitude pair required')
        for v,limit in zip(point,(90,180)):
            if isinstance(v,bool)or not isinstance(v,(int,float))or not math.isfinite(v)or abs(v)>limit:raise ValueError('Finite route coordinates required')
            values.append(math.floor(v*1000000+.5))
    return base64.urlsafe_b64encode(struct.pack('>Biiii',MODES.index(mode),*values)).decode().rstrip('=')


def decode(token):
    if not isinstance(token,str)or not re.fullmatch('[A-Za-z0-9_-]{23}',token):raise ValueError('Canonical compact route token required')
    raw=base64.urlsafe_b64decode(token+'=');mode,*values=struct.unpack('>Biiii',raw)
    if mode>=len(MODES):raise ValueError('Unknown route mode')
    pair=[[values[0]/1e6,values[1]/1e6],[values[2]/1e6,values[3]/1e6]]
    if encode(pair,MODES[mode])!=token:raise ValueError('Noncanonical compact route token')
    return pair,MODES[mode]


JS=r'''
    var routeParams=new URLSearchParams(window.location.search), rawRoute=routeParams.get("route"),
        mode=["fossgis_osrm_car","fossgis_osrm_bike","fossgis_osrm_foot"].indexOf(routeParams.get("engine"));
    if(window.location.pathname==="/directions" && rawRoute && mode>=0) {
      var values=rawRoute.split(/[;,]/).map(Number), visibleRoute=false;
      this.eachLayer(function(layer) {
        if(layer instanceof L.Polyline && !(layer instanceof L.Polygon) && layer.options.color==="#03f" && layer.getLatLngs().length>1) visibleRoute=true;
      });
      if(visibleRoute && values.length===4 && values.every(function(v,i){return Number.isFinite(v)&&Math.abs(v)<=(i%2?180:90);})) {
        var bytes=new Uint8Array(17),view=new DataView(bytes.buffer);bytes[0]=mode;
        values.forEach(function(v,i){view.setInt32(1+i*4,Math.round(v*1000000),false);});
        params.local_route=btoa(String.fromCharCode.apply(null,bytes)).replace(/\+/g,"-").replace(/\//g,"_").replace(/=+$/,"");
      }
    }
'''

RUBY='''    if params.key? :local_route
      token = params.delete(:local_route)
      raise ActionController::BadRequest unless token.is_a?(String) && token.match?(/\\A[A-Za-z0-9_-]{23}\\z/)
      raw = Base64.urlsafe_decode64(token + "=")
      raise ActionController::BadRequest unless raw.bytesize == 17 && Base64.urlsafe_encode64(raw, :padding => false) == token
      mode, a, b, c, d = raw.unpack("Cl>l>l>l>")
      raise ActionController::BadRequest unless mode < 3 && [a,c].all? { |v| v.abs <= 90000000 } && [b,d].all? { |v| v.abs <= 180000000 }
      raise ActionController::BadRequest if [:route,:engine,:node,:way,:relation,:changeset].any? { |key| params.key?(key) }
      new_params = { :engine => "fossgis_osrm_#{%w[car bike foot][mode]}",
                     :route => "#{a / 1000000.0},#{b / 1000000.0};#{c / 1000000.0},#{d / 1000000.0}",
                     :anchor => "map=#{zoom}/#{lat}/#{lon}" }
      redirect_to directions_path(new_params)
      return
    end
'''


def patch(map_source,controller):
    start=map_source.find('  getShortUrl: function (marker) {');end=map_source.find('  getGeoUri: function (marker) {',start)
    if start<0 or end<start or 'params.local_route'in map_source:raise ValueError('Native short link source changed')
    portion=map_source[start:end];anchor='    var query = Qs.stringify(params);'
    if portion.count(anchor)!=1:raise ValueError('Native query boundary changed')
    map_source=map_source[:start]+portion.replace(anchor,JS+'\n'+anchor)+map_source[end:]
    anchor='    lon, lat, zoom = ShortLink.decode(params[:code])\n'
    if controller.count(anchor)!=1 or 'params.key? :local_route'in controller:raise ValueError('Native short link controller changed')
    return map_source,'require "base64"\n'+controller.replace(anchor,anchor+RUBY)
