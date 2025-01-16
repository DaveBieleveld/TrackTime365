# Development Prompts

1. **Data Extraction & Validation**
   - Create script to extract events using @get_events.sql
   - Validate output against @events.schema.json
   - Test batch processing capabilities
   - Verify timezone handling

2. **Testing Tasks**
   - Run @main.py with future dates (2025)
   - Validate batch operations
   - Test timezone conversions
   - Check rate limiting behavior

3. **Performance Testing**
   - Monitor batch operation efficiency
   - Validate memory optimization
   - Test parallel processing
   - Measure API response times

4. **Integration Verification**
   - Test Office 365 connectivity
   - Validate database operations
   - Check category management
   - Verify error handling