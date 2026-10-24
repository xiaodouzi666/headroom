import { useMemo } from "react";
import { parse } from "diff2html";
import { Empty } from "./components";
export default function DiffView({ diff }: { diff: string }) {
  const files = useMemo(() => {
    try {
      return parse(diff);
    } catch {
      return [];
    }
  }, [diff]);
  if (!diff)
    return (
      <Empty title="No patch produced">
        A proposed diff appears here after the patch stage.
      </Empty>
    );
  if (!files.length) return <pre className="code-block">{diff}</pre>;
  return (
    <div className="diff-view">
      {files.map((file, index) => (
        <div className="diff-file" key={index}>
          <div className="diff-filename">{file.newName}</div>
          {file.blocks.map((block, b) => (
            <div key={b}>
              <div className="diff-hunk">{block.header}</div>
              {block.lines.map((line, n) => (
                <div className={`diff-line diff-${line.type}`} key={n}>
                  <span aria-hidden="true">{line.oldNumber ?? ""}</span>
                  <span aria-hidden="true">{line.newNumber ?? ""}</span>
                  <code>{line.content}</code>
                </div>
              ))}
            </div>
          ))}
        </div>
      ))}
    </div>
  );
}
