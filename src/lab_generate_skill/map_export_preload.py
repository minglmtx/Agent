"""Eager load native OSM export associations without changing its renderer.

The pinned controller's eight A/B responses on two independent deployments were
byte-identical. This changes database query batching, not data or task criteria.
"""
import hashlib

NATIVE_SHA256 = 'ed5cdb7ffee81b4243e74af2b3eceb1df4761a367ad216826dc5a3344c8c3234'
INSERT = '''
      # Verified association preloading; keep native rendering and record order.
      ActiveRecord::Associations::Preloader.new(:records => @nodes, :associations => { :changeset => :user }).call
      ActiveRecord::Associations::Preloader.new(:records => @ways, :associations => [{ :changeset => :user }, :nodes]).call
      ActiveRecord::Associations::Preloader.new(:records => @relations, :associations => [:relation_tags, :relation_members, { :changeset => :user }]).call
'''


def preload_controller(source):
    if hashlib.sha256(source.encode()).hexdigest() != NATIVE_SHA256:
        raise ValueError('Native OSM controller differs from the verified export implementation')
    anchor='      @relations.uniq!\n'
    if source.count(anchor)!=1:raise ValueError('Ambiguous export association preload position')
    return source.replace(anchor,anchor+INSERT)
