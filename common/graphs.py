import pydot

def path_to_edges(path):
    return [edge for edge in zip(path, path[1:])]

    
def iterpaths(graph_head, follow_func=None, partial=False, on_backwards=False):
    if follow_func is None:
        follow_func = lambda stack: stack[-1].following

    def make_yield(path, forward):
        if on_backwards:
            return path, forward
        return path

    def iterator(previous, node):
        current_path = previous + [node]
        
        if partial:
            yield make_yield(current_path, True)
        
        child_present = False
        for next in follow_func(current_path):
            for n in iterator(current_path, next):
                child_present = True
                yield n
                
        if not child_present and not partial:
            yield make_yield(current_path, True)
            if on_backwards:
                yield make_yield(current_path, False)
            return

        if on_backwards and partial:
            yield make_yield(current_path, False)

    for n in iterator([], graph_head):
        yield n


def iteredges(graph_head, follow_func=None):
    if follow_func is None:
        follow_func = lambda last: (((last, next), next) for next in last.following)
    
    visited = set()
    def follow(last):
        for next_edge, next_node in follow_func(last):
            if next_edge not in visited:
                yield next_edge, next_node
    
    def iterator(node):
        for next_edge, next_node in follow(node):
            visited.add(next_edge)
            yield next_edge
            for e in iterator(next_node):
                yield e

    return iterator(graph_head)


def iternodes(graph_head, follow_func=None):
    if follow_func is None:
        follow_func = lambda stack: stack[-1].following
    
    visited = set([graph_head])
    def follow(stack):
        for node in follow_func(stack):
            if node not in visited:
                visited.add(node) # XXX: is before yield correct?
                yield node
    
    for stack in iterpaths(graph_head, follow_func=follow, partial=True):
        yield stack[-1]

cfg_iterator = iternodes

def as_dot(filename, graph_head, marked_nodes=None, marked_edges=None):
    print('printing {0}'.format(filename))
    if marked_edges is None:
        marked_edges = []
    if marked_nodes is None:
        marked_nodes = []
        
    colors = ['red', 'blue', 'green', 'yellow', 'cyan', 'magenta']
    
    def get_colordict(groups):
        colordict = {}
        for color, group in zip(colors, groups):
            for element in group:
                colordict[element] = color
        return colordict
    
    node_colors = get_colordict(marked_nodes)
    edge_colors = get_colordict(marked_edges)
        
    graph = pydot.Dot('name')
    nodes_to_dot = {}
    for i, node in enumerate(iternodes(graph_head)):
        dotnode = pydot.Node('{0}'.format(i))
        label = '{0}'.format(node)
        dotnode.set_label(label)
        if node in node_colors:
            dotnode.set_color(node_colors[node])
        nodes_to_dot[node] = dotnode
        graph.add_node(dotnode)
    
    for edge in iteredges(graph_head):
        src, dst = edge
        dot_edge = pydot.Edge(nodes_to_dot[src], nodes_to_dot[dst])
        if edge in edge_colors:
            dot_edge.set_color(edge_colors[edge])
        graph.add_edge(dot_edge)
    
    graph.write(filename)
