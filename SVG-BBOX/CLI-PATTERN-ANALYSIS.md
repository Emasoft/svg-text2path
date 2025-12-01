# SVG-BBOX CLI Entry Point Pattern Analysis

## Executive Summary

The SVG-BBOX project has **six CLI tools** with **two distinct patterns** for
argument parsing:

1. **Manual Loop Pattern** (4 tools): Hand-coded `for` loops with manual flag
   parsing
2. **Utility Function Pattern** (1 tool): Uses the new `createArgParser()` from
   `lib/cli-utils.cjs`
3. **Interactive Main Entry** (1 tool): Top-level command dispatcher

This analysis examines current patterns, identifies inconsistencies, and
recommends standardization for Phase 4.

---

## Tool Overview

| Tool                     | Pattern     | Argument Parsing     | Help Display         | Main Function   | Lines  |
| ------------------------ | ----------- | -------------------- | -------------------- | --------------- | ------ |
| `sbb-fix-viewbox.cjs`    | Manual      | parseArgs() function | printHelp() function | async main()    | ~420   |
| `sbb-test.cjs`           | Manual      | Inline in runTest()  | showHelp() function  | async runTest() | ~480   |
| `sbb-getbbox.cjs`        | Utility     | createArgParser()    | Built into parser    | async main()    | ~800   |
| `sbb-chrome-getbbox.cjs` | Manual      | parseArgs() function | printHelp() function | async main()    | ~360   |
| `sbb-comparer.cjs`       | Manual      | parseArgs() function | printHelp() function | async main()    | ~2000+ |
| `sbb-extract.cjs`        | Manual      | parseArgs() function | printHelp() function | async main()    | ~2500+ |
| `svg-bbox.cjs`           | Interactive | Inline parsing       | printHelp() function | main()          | ~260   |

---

## Detailed Pattern Analysis

### Pattern 1: Manual Loop Argument Parsing

**Used by:** `sbb-fix-viewbox`, `sbb-test`, `sbb-chrome-getbbox`,
`sbb-comparer`, `sbb-extract`

#### Structure

```javascript
function parseArgs(argv) {
  const args = argv.slice(2);

  // Check for help/version first
  if (args.includes('--help') || args.includes('-h')) {
    printHelp();
    process.exit(0);
  }

  const positional = [];
  const options = {
    /* defaults */
  };

  for (let i = 0; i < args.length; i++) {
    const arg = args[i];

    if (arg === '--flag-name') {
      options.flagName = true;
    } else if (arg === '--value-flag') {
      options.valueFlag = args[++i];
    } else if (!arg.startsWith('-')) {
      positional.push(arg);
    }
  }

  return { ...options, positional };
}
```

#### Characteristics

- **Argument extraction**: `argv.slice(2)` directly in parseArgs
- **Help handling**: Check `includes()` before processing
- **Version handling**: Often done separately or inline
- **Loop technique**: Forward iteration with manual index management (`i++`)
- **Flag values**: Next argument accessed with `args[++i]` or `args[i+1]`
- **Error handling**: `process.exit(1)` or throws error

#### Tools Using This Pattern

**1. sbb-fix-viewbox.cjs**

- Lines 132-184
- Flags: `--auto-open`, `--force`, `--overwrite`, `--help`, `--version`
- Positional: `input`, `output` (optional, defaults to `input_fixed.svg`)
- Help check: Before entering loop
- Version: Checked in loop with separate `printVersion()`

**2. sbb-test.cjs**

- Lines 191-209 (inline in `runTest()`)
- Flags: `--help`, `--version`
- Positional: SVG file path
- Help check: Before processing (includes() style)
- Version: Separate check with early exit
- **Issue**: Help/version checked AFTER version info printed (line 203)

**3. sbb-chrome-getbbox.cjs**

- Lines 257-330
- Flags: `--margin`, `--json`, `--help`, `--version`
- Positional: `input`, `element-ids`
- Flag value handling: Split on `=` or use next argument
- **Issue**: Missing validation for flag combinations

**4. sbb-comparer.cjs**

- Lines 152-261
- Flags: 13+ flags including `--out-diff`, `--threshold`, `--alignment`,
  `--batch`, etc.
- Positional: `svg1`, `svg2`
- Loop index style: `for (let i = 2; i < argv.length; i++)` (includes
  node/script)
- **Issue**: Complex flag parsing with parameterized sub-modes
  (`--alignment object:id`, `--custom:x,y`)

**5. sbb-extract.cjs**

- Lines ~350-504 (in parseArgs function)
- Flags: 11+ flags including `--list`, `--rename`, `--extract`, `--export-all`
- Positional: Variable based on mode
- Mode detection: Based on flag presence
- **Issue**: Mode-specific validation spread across multiple conditional blocks

### Pattern 2: Utility Function - createArgParser()

**Used by:** `sbb-getbbox.cjs`

#### Structure

```javascript
const argParser = createArgParser({
  name: 'sbb-getbbox',
  description: 'Compute visual bounding boxes for SVG files and elements',
  usage: 'sbb-getbbox <svg-file> [object-ids...] [options]',
  flags: [
    {
      name: 'ignore-vbox',
      description: 'Compute full drawing bbox, ignoring viewBox clipping',
      type: 'boolean'
    },
    {
      name: 'dir',
      alias: 'd',
      description: 'Batch process all SVG files in directory',
      type: 'string'
    }
  ],
  minPositional: 0,
  maxPositional: Infinity
});

async function main() {
  const args = argParser(process.argv);
  // args = { flags: {...}, positional: [...] }
}
```

#### Characteristics

- **Configuration-driven**: Flag definitions in object literal
- **Built-in help/version**: Handled automatically by parser
- **Aliases support**: `-d` for `--dir`
- **Type validation**: `boolean` vs `string`
- **Error handling**: Parser throws descriptive errors
- **Return format**: `{ flags: {...}, positional: [...] }`

#### Advantages

- Consistent error messages
- Help/version automatically handled
- Built-in validation of positional counts
- Clear flag definitions
- Type safety for flags

#### Issues in Implementation

- Only used by 1 tool (sbb-getbbox)
- Not shared with other tools
- Mode detection still manual in main()

### Pattern 3: Interactive Entry Point

**Used by:** `svg-bbox.cjs`

#### Structure

```javascript
function main() {
  const args = process.argv.slice(2);

  if (args.includes('--version')) {
    printVersionInfo();
    process.exit(0);
  }

  if (args.length === 0 || args.includes('--help')) {
    printHelp();
    if (args.length === 0) {
      promptToolSelection(); // Interactive menu
    }
    process.exit(0);
  }
}

function promptToolSelection() {
  const rl = readline.createInterface({...});
  rl.question('> ', (answer) => {
    const tool = TOOLS[selection - 1];
    spawn('node', [`./${tool.name}.cjs`, '--help'], {stdio: 'inherit'});
  });
}
```

#### Characteristics

- **Menu-driven**: Spawns subprocess with tool selection
- **Tool registry**: TOOLS array with metadata
- **Tool discovery**: Lists available tools with descriptions
- **Help system**: Each tool can show detailed help via subprocess
- **Interactive**: Prompts user for tool selection

---

## Help Display Patterns

### Inline Help Functions

All tools define their own `printHelp()` or `showHelp()` function:

**sbb-fix-viewbox.cjs (lines 64-130)**

```javascript
function printHelp() {
  console.log(`
╔════════════════════════════════════════════════════════════════════════╗
║ sbb-fix-viewbox.cjs - Repair Missing SVG ViewBox & Dimensions         ║
╚════════════════════════════════════════════════════════════════════════╝

DESCRIPTION:
  ...
`);
}
```

**Characteristics:**

- ASCII art border (╔═╗║ etc.)
- Sections: DESCRIPTION, USAGE, ARGUMENTS, OPTIONS, EXAMPLES
- Inline in each file (not shared)
- Called from parseArgs() when `--help` detected
- `process.exit(0)` after printing

### Help Content Organization

| Section     | Purpose               | Consistency            |
| ----------- | --------------------- | ---------------------- |
| Header      | Tool name and purpose | ✓ Consistent format    |
| DESCRIPTION | What the tool does    | ✓ Present in all       |
| USAGE       | Command syntax        | ✓ Format varies        |
| ARGUMENTS   | Positional args       | ✓ Not always present   |
| OPTIONS     | Flags/options         | ✓ Format varies        |
| EXAMPLES    | Usage examples        | ✓ Format varies        |
| OUTPUT      | What tool produces    | ✗ Inconsistent/missing |

### Version Display

**Patterns observed:**

1. **Direct from function** (sbb-fix-viewbox)

   ```javascript
   printVersion('sbb-fix-viewbox');
   ```

2. **Inline from parseArgs** (sbb-test)

   ```javascript
   if (args.includes('--version') || args.includes('-v')) {
     console.log(`sbb-test v${getVersion()}`);
     process.exit(0);
   }
   ```

3. **Via printVersionInfo()** (svg-bbox)
   ```javascript
   function printVersionInfo() {
     console.log(`svg-bbox v${getVersion()}`);
   }
   ```

**Issues:**

- Version format inconsistent
- Some tools use `printVersion()` from version.cjs
- Others inline version output
- No standard format

---

## Main Function Structure

### Entry Point Patterns

**Pattern A: Named main() function**

```javascript
async function main() {
  const { input, output } = parseArgs(process.argv);
  // ...
}

runCLI(main); // from cli-utils.cjs
```

Used by: sbb-fix-viewbox, sbb-chrome-getbbox, sbb-getbbox, sbb-comparer

**Pattern B: Inline in exported function**

```javascript
async function runTest() {
  const args = process.argv.slice(2);
  // help/version check
  // main logic
}

runCLI(runTest);
```

Used by: sbb-test

**Pattern C: Direct IIFE**

```javascript
function main() {
  // synchronous
}

main();
```

Used by: svg-bbox

### Entry Point Characteristics

| Tool               | Function     | Type  | Error Handling    | Exit           |
| ------------------ | ------------ | ----- | ----------------- | -------------- |
| sbb-fix-viewbox    | main()       | async | runCLI() wrapper  | runCLI()       |
| sbb-test           | runTest()    | async | runCLI() wrapper  | runCLI()       |
| sbb-getbbox        | main()       | async | runCLI() wrapper  | runCLI()       |
| sbb-chrome-getbbox | main()       | async | runCLI() wrapper  | runCLI()       |
| sbb-comparer       | main()       | async | runCLI() wrapper  | runCLI()       |
| sbb-extract        | async main() | async | runCLI() wrapper  | runCLI()       |
| svg-bbox           | main()       | sync  | try/catch in main | process.exit() |

### Error Handling

**Primary mechanism**: `runCLI()` from lib/cli-utils.cjs

```javascript
async function runCLI(mainFn) {
  setupErrorHandlers();
  try {
    await mainFn();
  } catch (err) {
    if (err instanceof SVGBBoxError) {
      printError(err.message);
      if (err.details) console.error('Details:', err.details);
    } else {
      printError('Unexpected error');
      console.error(err.message || err);
    }
    const exitCode = getExitCode(err);
    process.exit(exitCode);
  }
}
```

**Characteristics:**

- Wraps main function
- Global error handlers for unhandled rejections/exceptions
- SVGBBoxError vs generic Error distinction
- Automatic exit code resolution
- Optional guidance hints

---

## Inconsistencies Identified

### 1. Argument Parsing

| Issue                              | Tools Affected                                           | Severity |
| ---------------------------------- | -------------------------------------------------------- | -------- |
| Manual loop duplicated 5 times     | sbb-fix-viewbox, test, chrome-getbbox, comparer, extract | High     |
| No consistent flag value handling  | chrome-getbbox uses `=`, others use space                | High     |
| Mode detection differs by tool     | extract has 4 modes, others have 1-2                     | High     |
| Help/version order varies          | sbb-test prints version before checking flags            | Medium   |
| Positional validation inconsistent | Some validate in loop, others in main                    | Medium   |

### 2. Help Display

| Issue                             | Severity | Impact                                  |
| --------------------------------- | -------- | --------------------------------------- |
| No shared help template           | High     | Maintenance burden, style inconsistency |
| Different section orders          | Medium   | User confusion when switching tools     |
| Output section missing/incomplete | Medium   | Users don't know what tool produces     |
| ASCII art header varies slightly  | Low      | Visual inconsistency                    |

### 3. Version Handling

| Issue                           | Severity |
| ------------------------------- | -------- |
| Three different approaches used | High     |
| No `--version` standardization  | Medium   |
| Version string format varies    | Medium   |

### 4. Code Organization

| Issue                                             | Severity |
| ------------------------------------------------- | -------- |
| parseArgs() appears 5 different times             | High     |
| Help functions not reusable                       | High     |
| No shared validation utilities                    | Medium   |
| Import patterns differ (getVersion, printVersion) | Medium   |

### 5. Main Function

| Issue                                              | Severity |
| -------------------------------------------------- | -------- |
| Entry point style varies (main vs runTest vs IIFE) | Low      |
| Some tools use runCLI(), svg-bbox doesn't          | Medium   |
| Error handling inconsistent in svg-bbox.cjs        | Medium   |

---

## Opportunities for Standardization (Phase 4)

### Opportunity 1: Universal Argument Parser

**Current State:**

- Manual parseArgs() in 5 tools
- createArgParser() only in 1 tool
- svg-bbox does inline parsing

**Recommendation:** Extend `createArgParser()` to handle:

- Multiple modes (list, extract, export, etc.)
- Multi-level flag validation
- Parameterized flags (e.g., `--alignment object:id`)
- Complex positional argument patterns

**Example:**

```javascript
const argParser = createArgParser({
  name: 'sbb-extract',
  description: 'Extract and rename SVG objects',
  modes: {
    list: {
      description: 'List all objects with previews',
      flags: [
        /* list-specific flags */
      ],
      positional: [{ name: 'input', required: true }]
    },
    extract: {
      description: 'Extract single object',
      flags: [
        /* extract-specific flags */
      ],
      positional: [
        { name: 'input', required: true },
        { name: 'id', required: true },
        { name: 'output', required: true }
      ]
    }
  }
});
```

### Opportunity 2: Shared Help System

**Current State:**

- Each tool has unique printHelp()
- No template or inheritance
- Help content inconsistently organized

**Recommendation:** Create reusable help component:

```javascript
function createHelpPrinter(config) {
  return function printHelp() {
    console.log(`
${formatHeader(config.name, config.description)}

${formatSection('DESCRIPTION', config.description)}
${formatSection('USAGE', config.usage)}
${formatSection('ARGUMENTS', config.arguments)}
${formatSection('OPTIONS', config.options)}
${formatSection('EXAMPLES', config.examples)}
${formatSection('OUTPUT', config.output)}
${formatSection('MODES', config.modes)}
    `);
  };
}
```

### Opportunity 3: Standardized Entry Point

**Current State:**

- Some use `runCLI(main)`
- Some use `main()`
- svg-bbox uses neither consistently

**Recommendation:** Standardize all tools to:

```javascript
async function main() {
  const args = argParser(process.argv);
  // implementation
}

runCLI(main); // Always use this wrapper
```

### Opportunity 4: Mode-Based Tool Refactoring

**Current State:**

- sbb-extract has modes but validation scattered
- sbb-comparer has modes with complex logic
- Others are single-mode

**Recommendation:** Create mode management system:

```javascript
class CLITool {
  constructor(config) {
    this.modes = new Map(Object.entries(config.modes));
    this.argParser = createArgParser(config);
  }

  async run(argv) {
    const args = this.argParser(argv);
    const mode = this.detectMode(args);
    await this.validateMode(mode, args);
    return this.modes.get(mode).handler(args);
  }
}
```

### Opportunity 5: Consolidated Version Handling

**Current State:**

- getVersion() from version.cjs (library pattern)
- printVersion() inconsistent
- Version output format varies

**Recommendation:** Standardize version display:

```javascript
function printVersion(toolName) {
  const version = getVersion();
  console.log(`${toolName} v${version} | svg-bbox toolkit`);
}

// All tools use: if (args.flags.version) printVersion('tool-name');
```

### Opportunity 6: Refactored Tool Distribution

**Current Structure (All as separate files):**

```
sbb-fix-viewbox.cjs      (parseArgs, printHelp, main - 420 lines)
sbb-test.cjs             (inline parsing - 480 lines)
sbb-getbbox.cjs          (createArgParser - 800 lines)
sbb-extract.cjs          (parseArgs, 4 modes - 2500+ lines)
sbb-comparer.cjs         (parseArgs, complex - 2000+ lines)
...
```

**Recommendation for Phase 4:** Create `lib/tools/` subdirectory:

```
lib/tools/
  ├── tool-factory.cjs          # CLITool base class
  ├── mode-manager.cjs          # Mode handling
  ├── arg-parser-extended.cjs   # Enhanced parser
  └── help-printer.cjs          # Help formatting

src/
  ├── fix-viewbox.cjs           # Smaller, cleaner
  ├── test.cjs
  ├── getbbox.cjs
  ├── extract.cjs               # Mode-based structure
  ├── comparer.cjs              # Mode-based structure
  └── ...
```

---

## Summary of Patterns

| Pattern                   | Tools       | LOC           | Reusability       | Maintainability     |
| ------------------------- | ----------- | ------------- | ----------------- | ------------------- |
| Manual parseArgs          | 5           | 100-200 each  | None (duplicated) | Poor (inconsistent) |
| createArgParser           | 1           | ~130          | High              | Good                |
| Inline parsing            | 1           | ~60           | None              | Fair                |
| **Total duplicated code** | **5 tools** | **~1000 LOC** | **None**          | **Poor**            |

---

## Recommendations (Priority Order)

### Phase 4 Roadmap

**Priority 1: Create Extended Argument Parser**

- Extend createArgParser() for modes and complex flags
- Move all 5 manual parseArgs() to use unified parser
- Estimated effort: 4-6 hours
- Impact: Eliminates 1000+ LOC duplication

**Priority 2: Standardize Help System**

- Create help printer factory
- Migrate all tools to use template-based help
- Estimated effort: 3-4 hours
- Impact: Consistent user experience, easier maintenance

**Priority 3: Refactor sbb-extract.cjs**

- Separate modes into distinct handlers
- Use extended argParser
- Reduce file size from 2500+ to ~1000 LOC
- Estimated effort: 6-8 hours
- Impact: Single largest maintenance burden reduced

**Priority 4: Refactor sbb-comparer.cjs**

- Simplify argument handling
- Extract complex logic to separate modules
- Use new help system
- Estimated effort: 4-6 hours
- Impact: Second largest file becomes maintainable

**Priority 5: Standardize Entry Points**

- Ensure all tools follow `runCLI(main)` pattern
- Consistent version handling
- Estimated effort: 2-3 hours
- Impact: Consistent error handling, exit codes

---

## File Size Analysis

After proposed refactoring (estimated):

| Tool                   | Current   | Proposed  | Reduction |
| ---------------------- | --------- | --------- | --------- |
| sbb-extract.cjs        | 2500+     | 1200      | 52%       |
| sbb-comparer.cjs       | 2000+     | 1100      | 45%       |
| sbb-getbbox.cjs        | 800       | 650       | 19%       |
| sbb-fix-viewbox.cjs    | 420       | 350       | 17%       |
| sbb-test.cjs           | 480       | 380       | 21%       |
| sbb-chrome-getbbox.cjs | 360       | 280       | 22%       |
| **Total**              | **~6560** | **~3960** | **40%**   |

---

## References

### Key Files Analyzed

1. **lib/cli-utils.cjs** (lines 1-247)
   - `createArgParser()` - Modern pattern
   - `runCLI()` - Error handling wrapper
   - Helper functions for output formatting

2. **sbb-fix-viewbox.cjs** (lines 132-184)
   - Example of manual parseArgs()
   - Help function (lines 64-130)
   - Entry point pattern (line 418)

3. **sbb-extract.cjs** (lines ~350-504)
   - Complex parseArgs() with modes
   - Multi-mode validation logic
   - Help function (lines 188-330+)

4. **sbb-getbbox.cjs** (lines 62-108)
   - Example of createArgParser()
   - Modern structured approach

5. **svg-bbox.cjs** (lines 1-260)
   - Interactive entry point
   - Tool registry pattern
   - Main help system

---

## Appendix: Pattern Comparison Matrix

### Argument Parsing

| Feature               | Manual Loop         | createArgParser         | Inline              |
| --------------------- | ------------------- | ----------------------- | ------------------- |
| Flag definition       | Scattered in loop   | Centralized config      | Scattered in loop   |
| Help/version handling | Explicit checks     | Built-in                | Explicit checks     |
| Error messages        | Custom/inconsistent | Standardized            | Custom/inconsistent |
| Type validation       | Manual              | Automatic (bool/string) | Manual              |
| Alias support         | None                | Yes                     | None                |
| Positional validation | Manual              | Automatic               | Manual              |
| Return format         | Object (varies)     | {flags, positional}     | Object (varies)     |
| Reusability           | None                | High                    | None                |

### Help Display

| Aspect       | sbb-fix-viewbox         | sbb-extract       | sbb-getbbox        |
| ------------ | ----------------------- | ----------------- | ------------------ |
| Format       | ASCII art header        | ASCII art header  | Built-in to parser |
| Organization | Sections in console.log | Multiple sections | Auto-generated     |
| Reusability  | None                    | None              | Partial (parser)   |
| Consistency  | Manual                  | Manual            | Automatic          |
| Maintenance  | High                    | High              | Low                |
