local state = require("srs.state")

local M = {}

local CLOZE_HL = "SrsCloze"

local EMPHASIS_PATTERN = "\\v%(\\*\\*\\*\\S.{-}\\*\\*\\*|\\*\\*\\S.{-}\\*\\*|\\*\\S.{-}\\*)"

local function blank(text)
	return string.rep(" ", #text)
end

local function scrub(line)
	line = line:gsub("\\.", blank)
	return (line:gsub("((`+)(.-)%2)", blank))
end

local function fence_marker(line)
	local content = line:gsub("^[ \t]*>+[ \t]*", "", 1)
	local marker = content:match("^[ \t]*(`+)") or content:match("^[ \t]*(~+)")
	if marker and #marker >= 3 then
		return marker
	end
end

local function emphasis_spans(line)
	local scrubbed = scrub(line)
	local spans = {}
	local init = 0
	while true do
		local match = vim.fn.matchstrpos(scrubbed, EMPHASIS_PATTERN, init)
		local text, start, stop = match[1], match[2], match[3]
		if not start or start < 0 then
			break
		end
		init = math.max(stop, start + 1)
		local delimiter = text:match("^%*+")
		local last = scrubbed:sub(stop - #delimiter, stop - #delimiter)
		if not last:match("%s") then
			spans[#spans + 1] = { start = start, stop = stop }
		end
	end
	return spans
end

local function cloze_mask(width)
	return string.rep("█", width)
end

local function mask_clozes(buf, lines)
	local fence = nil
	for row, line in ipairs(lines) do
		local marker = fence_marker(line)
		if fence then
			if marker and marker:sub(1, 1) == fence:sub(1, 1) and #marker >= #fence then
				fence = nil
			end
		elseif marker then
			fence = marker
		else
			for _, span in ipairs(emphasis_spans(line)) do
				local start_col, end_col = span.start + 1, span.stop
				local width = vim.fn.strdisplaywidth(line:sub(1, end_col))
					- vim.fn.strdisplaywidth(line:sub(1, start_col - 1))
				vim.api.nvim_buf_set_extmark(buf, state.ns, row - 1, start_col - 1, {
					virt_text = { { cloze_mask(width), CLOZE_HL } },
					virt_text_pos = "overlay",
					priority = 100,
				})
			end
		end
	end
end

local function fold_blocks(win, lines)
	local first, last = nil, nil
	local function flush()
		if first and last and last > first then
			state.win_cmd(win, string.format("silent! %d,%dfold", first, last))
		end
		first, last = nil, nil
	end
	for i, line in ipairs(lines) do
		if line:match("^%s*>") then
			if not first then
				first = i
			end
			last = i
		else
			flush()
		end
	end
	flush()
end

function M.open(card)
	vim.api.nvim_set_hl(0, CLOZE_HL, { link = "Comment", default = true })
	local win = state.win
	if not state.valid_win(win) then
		return nil
	end

	local abs = state.repo_root .. card.note
	local buf = vim.fn.bufadd(abs)
	vim.fn.bufload(buf)

	if state.buf ~= buf then
		state.clear_marks(state.buf)
		state.clear_folds(win)
		state.buf = buf
	end
	state.save_window(win)
	vim.api.nvim_win_set_buf(win, buf)

	vim.wo[win].foldmethod = "manual"
	vim.wo[win].foldenable = true

	state.clear_marks(buf)
	state.clear_folds(win)
	local lines = vim.api.nvim_buf_get_lines(buf, 0, -1, false)
	mask_clozes(buf, lines)
	fold_blocks(win, lines)
	vim.wo[win].foldlevel = 0

	if #lines > 0 then
		vim.api.nvim_win_set_cursor(win, { math.min(card.start_line, #lines), 0 })
	end
	return buf
end

function M.reveal(card)
	local buf, win = state.buf, state.win
	if not state.valid_buf(buf) then
		return
	end
	local last = math.min(card.end_line, vim.api.nvim_buf_line_count(buf))
	vim.api.nvim_buf_clear_namespace(buf, state.ns, card.start_line - 1, last)
	state.win_cmd(win, string.format("silent! %d,%dfoldopen!", card.start_line, last))
end

function M.statusline()
	local win = state.win
	if not state.valid_win(win) then
		return
	end
	local card = state.card
	local name = card.note:gsub("^/", "") .. " "
	local suffix = (state.paused and state.mode == "question") and " (PAUSED)" or ""
	local hint = state.mode == "rating" and " | n/e/i/o" or ""
	vim.wo[win].statusline = string.format(
		"[%d/%d] %s%s%s",
		card.index,
		card.total,
		name,
		suffix,
		hint
	)
end

return M
