from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt

@csrf_exempt
def drag_test(request):
    html_content = '''<!DOCTYPE html>
<html>
<head>
    <title>Drag Test</title>
    <style>
        .test-node {
            position: absolute;
            width: 150px;
            height: 100px;
            background: #007bff;
            color: white;
            border: 2px solid #0056b3;
            border-radius: 8px;
            padding: 10px;
            cursor: move;
            user-select: none;
            left: 100px;
            top: 100px;
        }
        .test-node.dragging {
            background: #dc3545;
            z-index: 1000;
        }
        .container {
            position: relative;
            width: 100%;
            height: 500px;
            border: 1px solid #ccc;
            margin: 20px;
        }
    </style>
</head>
<body>
    <h1>Simple Drag Test</h1>
    <div class="container">
        <div class="test-node" id="node1" data-node-id="test1">
            Test Node 1<br>
            <small>Drag me around</small>
        </div>
        <div class="test-node" id="node2" data-node-id="test2" style="left: 300px; top: 200px;">
            Test Node 2<br>
            <small>I'm draggable too</small>
        </div>
    </div>

    <script>
        console.log('=== DRAG TEST INITIALIZED ===');
        
        // Global drag state
        let dragState = {
            isDragging: false,
            dragElement: null,
            startX: 0,
            startY: 0,
            initialLeft: 0,
            initialTop: 0
        };
        
        // Get all test nodes
        const nodes = document.querySelectorAll('.test-node');
        console.log('Found nodes:', nodes.length);
        
        nodes.forEach(function(node) {
            console.log('Setting up node:', node.dataset.nodeId);
            
            node.addEventListener('mousedown', function(e) {
                console.log('🖱️ MOUSEDOWN on:', node.dataset.nodeId);
                
                dragState.isDragging = true;
                dragState.dragElement = node;
                dragState.startX = e.clientX;
                dragState.startY = e.clientY;
                dragState.initialLeft = parseInt(node.style.left) || 0;
                dragState.initialTop = parseInt(node.style.top) || 0;
                
                node.classList.add('dragging');
                
                e.preventDefault();
                console.log('Drag started at:', dragState.startX, dragState.startY);
            });
        });
        
        document.addEventListener('mousemove', function(e) {
            if (!dragState.isDragging || !dragState.dragElement) return;
            
            const deltaX = e.clientX - dragState.startX;
            const deltaY = e.clientY - dragState.startY;
            
            const newLeft = dragState.initialLeft + deltaX;
            const newTop = dragState.initialTop + deltaY;
            
            dragState.dragElement.style.left = newLeft + 'px';
            dragState.dragElement.style.top = newTop + 'px';
            
            console.log('Moving to:', newLeft, newTop);
        });
        
        document.addEventListener('mouseup', function(e) {
            if (!dragState.isDragging) return;
            
            console.log('🖱️ MOUSEUP - ending drag');
            
            dragState.dragElement.classList.remove('dragging');
            dragState.isDragging = false;
            dragState.dragElement = null;
        });
    </script>
</body>
</html>'''
    return HttpResponse(html_content)