"""Declared local PNG extension, preserving native Share form and controls.

Public current route geometry is submitted by the page; no task target or
private reference is injected. Unsupported raster formats are removed only in
this explicit PNG-only environment profile.
"""
import json
from urllib.parse import urlsplit
from .map_raster_request import export_byte_limit

REDIRECT='redirect_to "https://render.openstreetmap.org/cgi-bin/export?bbox=#{bbox}&scale=#{scale}&format=#{format}", :allow_other_host => true'
FORM='''    $("<input>")
      .attr("name", "format")'''
ROUTE = r'''
    $("<input>").attr("name", "local_route_geometry").attr("type", "hidden").appendTo($form);
    var currentRasterRoute = function () {
      var lines=[];
      map.eachLayer(function (layer) {
        if (layer instanceof L.Polyline && !(layer instanceof L.Polygon) &&
            layer.options.color === "#03f" && map.hasLayer(layer)) {
          var points=layer.getLatLngs();
          if (points.length > 1) lines.push(points.map(function(p) {return [p.lat,p.lng];}));
        }
      });
      if(lines.length>1) throw new Error("Ambiguous displayed native route");
      return lines.length ? lines[0] : [];
    };
    $form.data("labRasterRoute", currentRasterRoute);
    $form.on("submit.localRaster", function () {
      $(this).find("input[name=local_route_geometry]").val(JSON.stringify(currentRasterRoute()));
    });
'''


def patch(controller,share,endpoint, *, allow_pdf=False):
    u=urlsplit(endpoint)
    if u.scheme!='http'or u.hostname!='127.0.0.1'or not u.port or u.path!='/render'or u.query or u.fragment or u.username or u.password:
        raise ValueError('Owned local rendering endpoint required')
    if controller.count(REDIRECT)!=1 or share.count(FORM)!=1 or 'submit.localRaster'in share:
        raise ValueError('Native PNG source changed or extension installed twice')
    proxy='''raise ArgumentError, "PNG required" unless format == "png"
      payload = { :bbox => [params[:minlon],params[:minlat],params[:maxlon],params[:maxlat]],
                  :scale => scale, :format => format,
                  :route => JSON.parse(params[:local_route_geometry].presence || "[]") }
      target = URI(__ENDPOINT__)
      transport = Net::HTTP.new(target.host, target.port, nil)
      transport.open_timeout = 2
      transport.read_timeout = 95
      transport.max_retries = 0
      request = Net::HTTP::Post.new(target.request_uri)
      request["Content-Type"] = "application/json"
      request.body = payload.to_json
      response_body = +""
      transport.request(request) do |response|
        raise IOError, "Native local renderer unavailable" unless response.code == "200" && response["Content-Type"] == "image/png"
        response.read_body do |chunk|
          response_body << chunk
          raise IOError, "Raster response exceeds budget" if response_body.bytesize > 16777216
        end
      end
      response.headers["Cache-Control"] = "no-store"
      send_data response_body, :type => "image/png", :filename => "map.png", :disposition => "attachment"'''.replace('__ENDPOINT__',json.dumps(endpoint))
    if allow_pdf:
        proxy=proxy.replace('raise ArgumentError, "PNG required" unless format == "png"',
            'raise ArgumentError, "Unsupported format" unless ["png", "pdf"].include?(format)\n      content_type = format == "pdf" ? "application/pdf" : "image/png"')
        proxy=proxy.replace('response["Content-Type"] == "image/png"', 'response["Content-Type"] == content_type')
        proxy=proxy.replace('response_body.bytesize > 16777216',
            'response_body.bytesize > (format == "pdf" ? %d : %d)' %
            (export_byte_limit('pdf'), export_byte_limit('png')))
        proxy=proxy.replace(':type => "image/png", :filename => "map.png"', ':type => content_type, :filename => "map.#{format}"')
    controller='require "net/http"\nrequire "json"\n'+controller.replace(REDIRECT,proxy)
    share=share.replace(FORM,ROUTE+'\n'+FORM)
    for extension in ('jpeg','svg','pdf'):
        if extension=='pdf' and allow_pdf:continue
        label={'jpeg':'JPEG','svg':'SVG','pdf':'PDF'}[extension]
        anchor='\n        .append($("<option>").val("'+extension+'").text("'+label+'"))'
        if share.count(anchor)!=1:raise ValueError('Native format option changed')
        share=share.replace(anchor,'')
    return controller,share
