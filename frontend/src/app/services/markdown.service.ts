/**
 * Lightweight markdown-to-HTML renderer for AI-generated chapter content.
 *
 * Handles: headings, bold, italic, inline code, bullet/numbered lists with
 * nesting, horizontal rules, markdown tables, and paragraphs.
 */

const ESC_MAP: Record<string, string> = { '&': '&amp;', '<': '&lt;', '>': '&gt;' };

function esc(s: string): string {
  return s.replace(/[&<>]/g, (ch) => ESC_MAP[ch] || ch);
}

function inlineFormat(s: string): string {
  return esc(s)
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/(?<!\*)\*([^*]+?)\*(?!\*)/g, '<em>$1</em>')
    .replace(/`(.+?)`/g, '<code>$1</code>');
}

function stripBold(s: string): string {
  return s.replace(/\*\*/g, '');
}

/** Return true if the line is a table separator like |---|---|---| */
function isTableSeparator(line: string): boolean {
  return /^\|?[\s\-:|]+\|[\s\-:|]*\|?$/.test(line.trim());
}

/** Parse a table row into cells */
function parseTableRow(line: string): string[] {
  let trimmed = line.trim();
  if (trimmed.startsWith('|')) trimmed = trimmed.slice(1);
  if (trimmed.endsWith('|')) trimmed = trimmed.slice(0, -1);
  return trimmed.split('|').map(cell => cell.trim());
}

/** Check if a line looks like a table row (has at least 2 | characters) */
function isTableRow(line: string): boolean {
  const trimmed = line.trim();
  return trimmed.includes('|') && (trimmed.match(/\|/g) || []).length >= 2;
}

export function renderMarkdown(text: string): string {
  if (!text) return '';

  const lines = text.split('\n');
  const out: string[] = [];
  let inParagraph = false;
  const listStack: string[] = [];
  let i = 0;

  const closeAllLists = () => {
    while (listStack.length > 0) {
      out.push('</' + listStack.pop() + '>');
    }
  };
  const closeParagraph = () => {
    if (inParagraph) { out.push('</p>'); inParagraph = false; }
  };

  while (i < lines.length) {
    const raw = lines[i];
    const trimmed = raw.trimEnd();
    const stripped = trimmed.trim();

    // ── Horizontal rule ──
    if (/^-{3,}$|^\*{3,}$|^_{3,}$/.test(stripped)) {
      closeParagraph();
      closeAllLists();
      out.push('<hr>');
      i++;
      continue;
    }

    // ── Header ──
    const headerMatch = stripped.match(/^(#{1,5})\s+(.+)$/);
    if (headerMatch) {
      closeParagraph();
      closeAllLists();
      const level = Math.min(headerMatch[1].length + 1, 6); // # → h2, ## → h3, etc.
      const headerText = stripBold(headerMatch[2]).replace(/\s*#+\s*$/, ''); // strip trailing #
      out.push(`<h${level}>${esc(headerText)}</h${level}>`);
      i++;
      continue;
    }

    // ── Table ──
    // Detect table: current line is a table row, and next line is separator OR previous output was a table
    if (isTableRow(stripped)) {
      // Look ahead to see if this is actually a table (has separator within next 2 lines)
      let isSeparatorNearby = false;
      for (let look = 1; look <= 2 && i + look < lines.length; look++) {
        if (isTableSeparator(lines[i + look])) { isSeparatorNearby = true; break; }
      }
      // Also check if we already saw a separator (rows after separator)
      if (i > 0 && isTableSeparator(lines[i - 1])) isSeparatorNearby = true;
      if (i > 1 && isTableRow(lines[i - 1]) && isTableSeparator(lines[i - 1]) === false) {
        // Could be a data row after header+separator
        for (let look = -1; look >= -3 && i + look >= 0; look--) {
          if (isTableSeparator(lines[i + look])) { isSeparatorNearby = true; break; }
        }
      }

      if (isSeparatorNearby) {
        closeParagraph();
        closeAllLists();

        // Collect all consecutive table rows
        const tableLines: string[] = [];
        while (i < lines.length && (isTableRow(lines[i]) || isTableSeparator(lines[i]))) {
          tableLines.push(lines[i]);
          i++;
        }

        out.push('<div class="table-wrap"><table>');

        let isHeader = true;
        for (const tl of tableLines) {
          if (isTableSeparator(tl)) {
            isHeader = false;
            continue;
          }
          const cells = parseTableRow(tl);
          const tag = isHeader ? 'th' : 'td';
          const rowTag = isHeader ? 'thead' : '';
          if (isHeader) out.push('<thead>');
          out.push('<tr>');
          for (const cell of cells) {
            out.push(`<${tag}>${inlineFormat(cell)}</${tag}>`);
          }
          out.push('</tr>');
          if (isHeader) { out.push('</thead><tbody>'); isHeader = false; }
        }
        out.push('</tbody></table></div>');
        continue;
      }
    }

    // ── List item ──
    const listMatch = stripped.length > 0 ? raw.match(/^(\s*)([-*]|\d+[.)]) (.+)$/) : null;
    if (listMatch) {
      closeParagraph();
      const indent = listMatch[1].length;
      const isOrdered = /^\d+[.)]/.test(listMatch[2]);
      const listType = isOrdered ? 'ol' : 'ul';
      const targetDepth = Math.floor(indent / 2) + 1;

      // Close deeper lists
      while (listStack.length > targetDepth) {
        out.push('</' + listStack.pop() + '>');
      }
      // Open new list if needed
      while (listStack.length < targetDepth) {
        out.push('<' + listType + '>');
        listStack.push(listType);
      }
      // Switch list type if different at same depth
      if (listStack.length === targetDepth && listStack[listStack.length - 1] !== listType) {
        out.push('</' + listStack.pop() + '>');
        out.push('<' + listType + '>');
        listStack.push(listType);
      }

      out.push('<li>' + inlineFormat(listMatch[3]) + '</li>');
      i++;
      continue;
    }

    // ── End of list context ──
    if (listStack.length > 0) {
      closeAllLists();
    }

    // ── Empty line ──
    if (stripped === '') {
      closeParagraph();
      i++;
      continue;
    }

    // ── Regular text ──
    if (!inParagraph) {
      out.push('<p>');
      inParagraph = true;
    } else {
      out.push('<br>');
    }
    out.push(inlineFormat(stripped));
    i++;
  }

  closeParagraph();
  closeAllLists();
  return out.join('');
}
