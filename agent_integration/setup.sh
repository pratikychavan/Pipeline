#!/bin/bash
# Quick setup script for agent integration

echo "================================================"
echo "Agent Integration Setup"
echo "================================================"
echo ""

# Step 1: Check if we're in the right directory
if [ ! -f "manage.py" ]; then
    echo "❌ Error: manage.py not found. Please run from Django project root."
    exit 1
fi

echo "✓ Found Django project"
echo ""

# Step 2: Update settings.py
echo "Step 1: Updating settings.py..."
if grep -q "agent_integration" pipeline/settings.py; then
    echo "✓ agent_integration already in INSTALLED_APPS"
else
    echo "  Adding agent_integration to INSTALLED_APPS..."
    sed -i "/INSTALLED_APPS = \[/,/\]/s/    'core',/    'core',\n    'agent_integration',/" pipeline/settings.py
    echo "✓ Added to INSTALLED_APPS"
fi
echo ""

# Step 3: Update urls.py
echo "Step 2: Updating urls.py..."
if grep -q "agent_integration" pipeline/urls.py; then
    echo "✓ agent_integration URLs already configured"
else
    echo "  Adding agent URLs..."
    sed -i "/urlpatterns = \[/a\    path('agent/', include('agent_integration.urls'))," pipeline/urls.py
    echo "✓ Added URL configuration"
fi
echo ""

# Step 4: Create migrations
echo "Step 3: Creating migrations..."
python manage.py makemigrations agent_integration
if [ $? -eq 0 ]; then
    echo "✓ Migrations created"
else
    echo "❌ Failed to create migrations"
    exit 1
fi
echo ""

# Step 5: Run migrations
echo "Step 4: Running migrations..."
python manage.py migrate agent_integration
if [ $? -eq 0 ]; then
    echo "✓ Migrations applied"
else
    echo "❌ Failed to apply migrations"
    exit 1
fi
echo ""

# Step 6: Verify installation
echo "Step 5: Verifying installation..."
python manage.py check
if [ $? -eq 0 ]; then
    echo "✓ System check passed"
else
    echo "❌ System check failed"
    exit 1
fi
echo ""

echo "================================================"
echo "✅ Agent Integration Setup Complete!"
echo "================================================"
echo ""
echo "Next steps:"
echo "1. Start server: python manage.py runserver"
echo "2. Visit admin: http://localhost:8000/admin/"
echo "3. Test API: curl http://localhost:8000/agent/runs/..."
echo ""
echo "Documentation:"
echo "- README: agent_integration/README.md"
echo "- Integration Guide: agent_integration/INTEGRATION.md"
echo "- Implementation Summary: agent_integration/IMPLEMENTATION_SUMMARY.md"
echo ""
echo "Run tests with: python manage.py test agent_integration"
echo ""
