"""Public implementation metadata only; never exposes company or financial data."""
BASE_FEATURES=('low_stock_reorder','party_price_history','party_payment_terms','master_lifecycle','party_shipping_address','party_credit_limits','recurring_drafts','master_edit_revisions')

def install(app,m):
    @app.get('/api/capabilities')
    def capabilities():
        features=list(BASE_FEATURES)
        if hasattr(m.Company,'book_label'):features.append('company_book_labels')
        limits={}
        if getattr(app.state,'document_attachments_ready',False) and getattr(app.state,'chunked_backups_ready',False):
            features.append('document_attachments')
            from attachment_limits import public_limits
            limits=public_limits()
        formats={'import':['apex-json-v6','apex-json-v7'],'export':['apex-json-v7']}
        if getattr(app.state,'chunked_backups_ready',False):
            features.append('chunked_backups')
            formats['import'].append('apex-zip-v8');formats['export'].append('apex-zip-v8')
        return {'api_version':app.version,'build_revision':m.BUILD_REVISION,'capabilities_version':1,'supported_features':features,
                'backup_formats':formats,'business_timezone':'Asia/Kolkata','limits':limits}
