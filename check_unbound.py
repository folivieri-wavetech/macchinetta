import ast
import sys

def check_unbound(filename):
    with open(filename, 'r', encoding='utf-8') as f:
        tree = ast.parse(f.read(), filename=filename)

    class Analyzer(ast.NodeVisitor):
        def __init__(self):
            self.issues = []
            self.current_scope = set()
            self.scope_stack = []

        def push_scope(self):
            self.scope_stack.append(self.current_scope.copy())

        def pop_scope(self):
            self.current_scope = self.scope_stack.pop()

        def visit_FunctionDef(self, node):
            old_scope = self.current_scope.copy()
            self.current_scope = set()
            for arg in node.args.args:
                self.current_scope.add(arg.arg)
            self.generic_visit(node)
            self.current_scope = old_scope

        def visit_Name(self, node):
            if isinstance(node.ctx, ast.Store):
                self.current_scope.add(node.id)
            elif isinstance(node.ctx, ast.Load):
                if node.id not in self.current_scope:
                    # Ignore builtins and global modules for this simple check
                    if node.id not in __builtins__ and node.id not in ['pd', 'time', 'requests', 'sys', 'os']:
                        pass # too noisy to report here, better to do flow analysis
            self.generic_visit(node)

    # Simple flow analysis is hard. Let's use pylint instead which has E0601 (used-before-assignment).
    print("Use pylint for better analysis")

if __name__ == "__main__":
    check_unbound(sys.argv[1])
