"""Preserve native OSM feature selection while indexing repeated membership.

The original renderer checks every way and relation for every node. The
indexed branch uses the same object references, tag tests, and feature order;
the original three-argument interestingNode interface remains supported.
"""
import hashlib

VERSION = 'native-osm-renderer-membership-index-v1'
PINNED_SHA256 = '19c69de257efcd54351f6344b8c3290fe9bbd2281312434a08f9a2d23d02f530'

BUILD_BEFORE = '''    for (var node_id in nodes) {
      var node = nodes[node_id];
      if (this.interestingNode(node, ways, relations)) {
        features.push(node);
      }
    }'''
BUILD_AFTER = '''    var membership = {wayNodes: new Set(), relationNodes: new Set()};
    for (var wi = 0; wi < ways.length; wi++) {
      for (var wn = 0; wn < ways[wi].nodes.length; wn++) {
        membership.wayNodes.add(ways[wi].nodes[wn]);
      }
    }
    for (var ri = 0; ri < relations.length; ri++) {
      for (var rn = 0; rn < relations[ri].members.length; rn++) {
        membership.relationNodes.add(relations[ri].members[rn]);
      }
    }

    for (var node_id in nodes) {
      var node = nodes[node_id];
      if (this.interestingNode(node, ways, relations, membership)) {
        features.push(node);
      }
    }'''
INTERESTING_BEFORE = '''  interestingNode: function (node, ways, relations) {
    var used = false;

    for (var i = 0; i < ways.length; i++) {
      if (ways[i].nodes.indexOf(node) >= 0) {
        used = true;
        break;
      }
    }

    if (!used) {
      return true;
    }

    for (var i = 0; i < relations.length; i++) {
      if (relations[i].members.indexOf(node) >= 0)
        return true;
    }'''
INTERESTING_AFTER = '''  interestingNode: function (node, ways, relations, membership) {
    var used = false;

    if (membership) {
      used = membership.wayNodes.has(node);
    } else {
      for (var i = 0; i < ways.length; i++) {
        if (ways[i].nodes.indexOf(node) >= 0) {
          used = true;
          break;
        }
      }
    }

    if (!used) {
      return true;
    }

    if (membership) {
      if (membership.relationNodes.has(node)) return true;
    } else {
      for (var i = 0; i < relations.length; i++) {
        if (relations[i].members.indexOf(node) >= 0)
          return true;
      }
    }'''


def patch_source(source):
    if hashlib.sha256(source.encode()).hexdigest() != PINNED_SHA256:
        raise ValueError('Exact pinned original native OSM renderer required')
    for before in (BUILD_BEFORE, INTERESTING_BEFORE):
        if source.count(before) != 1:
            raise ValueError('Native renderer membership boundary changed')
    return source.replace(BUILD_BEFORE, BUILD_AFTER).replace(INTERESTING_BEFORE, INTERESTING_AFTER)


def require_exact_private_source(original, private, tile_url):
    expected = patch_source(original)
    old = 'http://ogma.lti.cs.cmu.edu:8080/tile/'
    if tile_url:
        if expected.count(old) != 2:
            raise ValueError('Original native tile URL boundary changed')
        expected = expected.replace(old, tile_url + '/tile/')
    if private != expected:
        raise ValueError('Private renderer differs from exact indexed native source')
    return {
        'version': VERSION,
        'original_sha256': PINNED_SHA256,
        'private_sha256': hashlib.sha256(private.encode()).hexdigest(),
        'payload_reduced': False,
        'feature_order_changed': False,
        'styles_changed': False,
        'node_object_identity_preserved': True,
        'three_argument_fallback_preserved': True,
    }
