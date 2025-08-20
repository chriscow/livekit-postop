#!/usr/bin/env python3
"""
Medical Knowledge Management CLI Tool

This tool provides CRUD operations for managing the Redis-based medical knowledge
database used by the PostOp AI system.

Usage:
    python tools/medical_knowledge_cli.py list
    python tools/medical_knowledge_cli.py view <id>
    python tools/medical_knowledge_cli.py add --text "Medical information here" --category "wound_care"
    python tools/medical_knowledge_cli.py edit <id> --text "Updated information"
    python tools/medical_knowledge_cli.py delete <id>
    python tools/medical_knowledge_cli.py search "keyword"
    python tools/medical_knowledge_cli.py stats
    python tools/medical_knowledge_cli.py export knowledge.json
    python tools/medical_knowledge_cli.py import knowledge.json
    python tools/medical_knowledge_cli.py clear --confirm
"""

import asyncio
import json
import uuid
import os
from typing import Dict, List, Optional

import click
import redis
from dotenv import load_dotenv
from tabulate import tabulate

from discharge.medical_knowledge import create_medical_knowledge_handler


class MedicalKnowledgeManager:
    """Manages Redis-based medical knowledge database operations"""
    
    def __init__(self, redis_url: str = None):
        if not redis_url:
            redis_url = os.getenv('REDIS_URL', 'redis://redis:6379/0')
        
        self.redis_client = redis.from_url(redis_url)
        self.knowledge_prefix = "medical_knowledge:"
        
        # Test connection
        try:
            self.redis_client.ping()
        except Exception as e:
            click.echo(f"❌ Failed to connect to Redis: {e}", err=True)
            raise
    
    def list_all_knowledge(self) -> List[Dict]:
        """List all knowledge entries"""
        try:
            keys = self.redis_client.keys(f"{self.knowledge_prefix}*")
            entries = []
            
            for key in keys:
                entry_data = self.redis_client.hgetall(key)
                if entry_data:
                    entries.append({
                        'id': entry_data.get(b'id', b'').decode('utf-8'),
                        'text': entry_data.get(b'text', b'').decode('utf-8'),
                        'category': entry_data.get(b'category', b'general').decode('utf-8')
                    })
            
            return entries
        except Exception as e:
            click.echo(f"❌ Error listing knowledge: {e}", err=True)
            return []
    
    def get_knowledge(self, knowledge_id: str) -> Optional[Dict]:
        """Get specific knowledge entry"""
        try:
            key = f"{self.knowledge_prefix}{knowledge_id}"
            entry_data = self.redis_client.hgetall(key)
            
            if not entry_data:
                return None
                
            return {
                'id': entry_data.get(b'id', b'').decode('utf-8'),
                'text': entry_data.get(b'text', b'').decode('utf-8'),
                'category': entry_data.get(b'category', b'general').decode('utf-8')
            }
        except Exception as e:
            click.echo(f"❌ Error getting knowledge: {e}", err=True)
            return None
    
    def add_knowledge(self, text: str, category: str = "general", knowledge_id: str = None) -> str:
        """Add new knowledge entry"""
        try:
            if not knowledge_id:
                knowledge_id = str(uuid.uuid4())
            
            key = f"{self.knowledge_prefix}{knowledge_id}"
            
            self.redis_client.hset(key, mapping={
                'id': knowledge_id,
                'text': text,
                'category': category
            })
            
            return knowledge_id
        except Exception as e:
            click.echo(f"❌ Error adding knowledge: {e}", err=True)
            raise
    
    def update_knowledge(self, knowledge_id: str, text: str = None, category: str = None) -> bool:
        """Update existing knowledge entry"""
        try:
            key = f"{self.knowledge_prefix}{knowledge_id}"
            
            # Check if entry exists
            if not self.redis_client.exists(key):
                return False
            
            updates = {}
            if text:
                updates['text'] = text
            if category:
                updates['category'] = category
            
            if updates:
                self.redis_client.hset(key, mapping=updates)
            
            return True
        except Exception as e:
            click.echo(f"❌ Error updating knowledge: {e}", err=True)
            return False
    
    def delete_knowledge(self, knowledge_id: str) -> bool:
        """Delete knowledge entry"""
        try:
            key = f"{self.knowledge_prefix}{knowledge_id}"
            result = self.redis_client.delete(key)
            return result > 0
        except Exception as e:
            click.echo(f"❌ Error deleting knowledge: {e}", err=True)
            return False
    
    def search_knowledge(self, query: str) -> List[Dict]:
        """Search knowledge entries"""
        entries = self.list_all_knowledge()
        query_lower = query.lower()
        
        matches = []
        for entry in entries:
            if query_lower in entry['text'].lower() or query_lower in entry['category'].lower():
                matches.append(entry)
        
        return matches
    
    def get_stats(self) -> Dict:
        """Get knowledge database statistics"""
        entries = self.list_all_knowledge()
        categories = {}
        
        for entry in entries:
            category = entry['category']
            categories[category] = categories.get(category, 0) + 1
        
        return {
            'total_entries': len(entries),
            'categories': categories
        }
    
    def clear_all_knowledge(self) -> int:
        """Clear all knowledge entries"""
        try:
            keys = self.redis_client.keys(f"{self.knowledge_prefix}*")
            if keys:
                return self.redis_client.delete(*keys)
            return 0
        except Exception as e:
            click.echo(f"❌ Error clearing knowledge: {e}", err=True)
            return 0
    
    def export_knowledge(self, filename: str):
        """Export knowledge to JSON file"""
        entries = self.list_all_knowledge()
        
        with open(filename, 'w') as f:
            json.dump(entries, f, indent=2)
        
        return len(entries)
    
    def import_knowledge(self, filename: str) -> int:
        """Import knowledge from JSON file"""
        with open(filename, 'r') as f:
            entries = json.load(f)
        
        imported = 0
        for entry in entries:
            try:
                self.add_knowledge(
                    text=entry['text'],
                    category=entry.get('category', 'general'),
                    knowledge_id=entry.get('id')
                )
                imported += 1
            except Exception as e:
                click.echo(f"⚠️  Failed to import entry: {e}")
        
        return imported


# CLI Commands
@click.group()
@click.pass_context
def cli(ctx):
    """Medical Knowledge Management CLI"""
    load_dotenv()
    
    try:
        ctx.ensure_object(dict)
        ctx.obj['manager'] = MedicalKnowledgeManager()
    except Exception as e:
        click.echo(f"❌ Failed to initialize: {e}")
        ctx.exit(1)


@cli.command()
@click.option('--limit', '-l', default=20, help='Maximum number of entries to show')
@click.pass_context
def list(ctx, limit):
    """List all medical knowledge entries"""
    manager = ctx.obj['manager']
    entries = manager.list_all_knowledge()
    
    if not entries:
        click.echo("📋 No medical knowledge entries found")
        return
    
    # Prepare table data
    table_data = []
    for entry in entries[:limit]:
        text_preview = entry['text'][:80] + "..." if len(entry['text']) > 80 else entry['text']
        table_data.append([
            entry['id'][:8] + "...",
            entry['category'],
            text_preview
        ])
    
    click.echo(f"📚 Found {len(entries)} medical knowledge entries (showing {min(limit, len(entries))}):")
    click.echo(tabulate(table_data, headers=["ID", "Category", "Text"], tablefmt="grid"))


@cli.command()
@click.argument('knowledge_id')
@click.pass_context
def view(ctx, knowledge_id):
    """View specific knowledge entry"""
    manager = ctx.obj['manager']
    entry = manager.get_knowledge(knowledge_id)
    
    if not entry:
        click.echo(f"❌ Knowledge entry '{knowledge_id}' not found")
        return
    
    click.echo(f"📄 Knowledge Entry: {entry['id']}")
    click.echo(f"📂 Category: {entry['category']}")
    click.echo(f"📝 Text:\n{entry['text']}")


@cli.command()
@click.option('--text', '-t', required=True, help='Knowledge text content')
@click.option('--category', '-c', default='general', help='Knowledge category')
@click.pass_context
def add(ctx, text, category):
    """Add new medical knowledge entry"""
    manager = ctx.obj['manager']
    
    try:
        knowledge_id = manager.add_knowledge(text, category)
        click.echo(f"✅ Added knowledge entry: {knowledge_id}")
        click.echo(f"📂 Category: {category}")
        click.echo(f"📝 Text: {text[:100]}..." if len(text) > 100 else f"📝 Text: {text}")
    except Exception as e:
        click.echo(f"❌ Failed to add knowledge: {e}")


@cli.command()
@click.argument('knowledge_id')
@click.option('--text', '-t', help='Updated knowledge text')
@click.option('--category', '-c', help='Updated category')
@click.pass_context
def edit(ctx, knowledge_id, text, category):
    """Edit existing knowledge entry"""
    manager = ctx.obj['manager']
    
    if not text and not category:
        click.echo("❌ Must provide either --text or --category to update")
        return
    
    success = manager.update_knowledge(knowledge_id, text, category)
    
    if success:
        click.echo(f"✅ Updated knowledge entry: {knowledge_id}")
    else:
        click.echo(f"❌ Knowledge entry '{knowledge_id}' not found")


@cli.command()
@click.argument('knowledge_id')
@click.option('--confirm', is_flag=True, help='Confirm deletion')
@click.pass_context
def delete(ctx, knowledge_id, confirm):
    """Delete knowledge entry"""
    manager = ctx.obj['manager']
    
    # Show entry before deletion
    entry = manager.get_knowledge(knowledge_id)
    if not entry:
        click.echo(f"❌ Knowledge entry '{knowledge_id}' not found")
        return
    
    if not confirm:
        click.echo(f"📄 Entry to delete: {entry['id']}")
        click.echo(f"📂 Category: {entry['category']}")
        click.echo(f"📝 Text: {entry['text'][:100]}...")
        click.echo("⚠️  Use --confirm to actually delete this entry")
        return
    
    success = manager.delete_knowledge(knowledge_id)
    
    if success:
        click.echo(f"✅ Deleted knowledge entry: {knowledge_id}")
    else:
        click.echo(f"❌ Failed to delete knowledge entry: {knowledge_id}")


@cli.command()
@click.argument('query')
@click.pass_context
def search(ctx, query):
    """Search medical knowledge"""
    manager = ctx.obj['manager']
    matches = manager.search_knowledge(query)
    
    if not matches:
        click.echo(f"📋 No matches found for: {query}")
        return
    
    click.echo(f"🔍 Found {len(matches)} matches for '{query}':")
    
    table_data = []
    for entry in matches:
        text_preview = entry['text'][:80] + "..." if len(entry['text']) > 80 else entry['text']
        table_data.append([
            entry['id'][:8] + "...",
            entry['category'],
            text_preview
        ])
    
    click.echo(tabulate(table_data, headers=["ID", "Category", "Text"], tablefmt="grid"))


@cli.command()
@click.pass_context
def stats(ctx):
    """Show knowledge database statistics"""
    manager = ctx.obj['manager']
    stats = manager.get_stats()
    
    click.echo("📊 Medical Knowledge Database Statistics:")
    click.echo(f"📚 Total entries: {stats['total_entries']}")
    click.echo()
    
    if stats['categories']:
        click.echo("📂 Categories:")
        table_data = [[cat, count] for cat, count in stats['categories'].items()]
        click.echo(tabulate(table_data, headers=["Category", "Count"], tablefmt="grid"))
    else:
        click.echo("📂 No categories found")


@cli.command()
@click.argument('filename')
@click.pass_context
def export(ctx, filename):
    """Export knowledge to JSON file"""
    manager = ctx.obj['manager']
    
    try:
        count = manager.export_knowledge(filename)
        click.echo(f"✅ Exported {count} entries to {filename}")
    except Exception as e:
        click.echo(f"❌ Export failed: {e}")


@cli.command()
@click.argument('filename')
@click.pass_context
def import_cmd(ctx, filename):
    """Import knowledge from JSON file"""
    manager = ctx.obj['manager']
    
    try:
        count = manager.import_knowledge(filename)
        click.echo(f"✅ Imported {count} entries from {filename}")
    except Exception as e:
        click.echo(f"❌ Import failed: {e}")


@cli.command()
@click.option('--confirm', is_flag=True, help='Confirm clearing all data')
@click.pass_context
def clear(ctx, confirm):
    """Clear all medical knowledge (use with caution!)"""
    manager = ctx.obj['manager']
    
    if not confirm:
        stats = manager.get_stats()
        click.echo(f"⚠️  This will delete ALL {stats['total_entries']} medical knowledge entries!")
        click.echo("⚠️  Use --confirm to actually clear the database")
        return
    
    deleted = manager.clear_all_knowledge()
    click.echo(f"🗑️  Cleared {deleted} medical knowledge entries")


# Register import command with proper name
cli.add_command(import_cmd, name='import')


if __name__ == '__main__':
    cli()