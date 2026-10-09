using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Security.Cryptography;
using System.Text.Json;
using System.Xml;
using System.Xml.Linq;

namespace unforge
{
	public static class RecordExporter
	{
		public const string ToolVersion = "v4.0.87-os1";
		public const string ManifestName = ".unforge-export.json";
		private const int ProgressInterval = 5000;
		private static readonly HashSet<string> AllowedGuards = new() { "struct_cycle", "record_cycle", "empty_structure", "null_pointer", "null_array" };

		public static void Save(DataForge forge, string filename)
		{
			var output = Path.GetFullPath(Path.GetDirectoryName(filename));
			var manifestPath = Path.Combine(output, ManifestName);
			if (File.Exists(manifestPath) || Directory.Exists(Path.Combine(output, "libs")))
				throw new IOException("Export requires a fresh output directory");
			if (forge.RecordDefinitionCount <= 0 || forge.ReferenceToRecordMap.Count != forge.RecordDefinitionCount)
				throw new InvalidDataException("Invalid or duplicate binary record IDs");
			var canonicalPaths = forge.PathToRecordMap.Keys.Select(path => path.Replace('\\', '/')).ToHashSet(StringComparer.OrdinalIgnoreCase);
			var usedPaths = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
			var seen = new HashSet<Guid>();
			var entries = new List<object>();
			var guards = new Dictionary<string, long>();
			var emptyRecords = 0;
			for (var recordIndex = 0; recordIndex < forge.RecordDefinitionCount; recordIndex++)
			{
				var definition = forge.ReadRecordDefinitionAtIndex(recordIndex);
				if (!seen.Add(definition.Hash)) throw new InvalidDataException("Duplicate record ID");
				var canonical = forge.PathToRecordMap[definition.FileName] == recordIndex;
				var original = definition.FileName.Replace('\\', '/');
				SafePath(output, original);
				var relative = canonical ? original : original[..(original.LastIndexOf('/') + 1)] + definition.Hash + ".xml";
				if ((!canonical && canonicalPaths.Contains(relative)) || !usedPaths.Add(relative))
					throw new InvalidDataException("Output path collision: " + relative);
				var path = SafePath(output, relative);
				if (File.Exists(path) || Directory.Exists(path)) throw new IOException("Output already exists: " + relative);
				forge.Diagnostics.Clear();
				var root = forge.ReadRecordByReferenceAsXml(new XmlDocument(), definition.Hash);
				var empty = root == null;
				if (empty)
				{
					if (!forge.Diagnostics.ContainsKey("empty_structure") || forge.Diagnostics.Keys.Any(key => key != "empty_structure"))
						throw new InvalidDataException("Null record body without empty-structure proof");
					root = new XmlDocument().CreateElement(DataForgeRecordDefinition.XmlName(definition.Name));
					root.SetAttribute("__ref", definition.Hash.ToString());
					root.SetAttribute("__path", definition.FileName);
					root.SetAttribute("__type", definition.StructDefinition.Name);
					if (forge.FileVersion >= 8) root.SetAttribute("__team", definition.DevTeamName);
					if (root.Name != definition.Name) root.SetAttribute("__recordName", definition.Name);
					emptyRecords++;
				}
				if (forge.Diagnostics.Keys.Any(key => !AllowedGuards.Contains(key)) || HasErrors(XElement.Parse(root.OuterXml)))
					throw new InvalidDataException("Export error or truncation in record " + definition.Hash + ": " + JsonSerializer.Serialize(forge.Diagnostics));
				if (root.GetAttribute("__ref") != definition.Hash.ToString() || root.GetAttribute("__path") != definition.FileName ||
					root.GetAttribute("__type") != definition.StructDefinition.Name || root.Name != DataForgeRecordDefinition.XmlName(definition.Name) ||
					(root.Name != definition.Name && root.GetAttribute("__recordName") != definition.Name))
					throw new InvalidDataException("Record metadata mismatch");
				Directory.CreateDirectory(Path.GetDirectoryName(path));
				using (var stream = File.Create(path))
				using (var writer = XmlWriter.Create(stream, new XmlWriterSettings { OmitXmlDeclaration = true, Indent = true, IndentChars = "  ", NewLineChars = "\r\n" }))
					root.WriteTo(writer);
				var parsed = XDocument.Load(path).Root;
				if (parsed.Attribute("__ref")?.Value != definition.Hash.ToString() || HasErrors(parsed))
					throw new InvalidDataException("Serialized record failed validation");
				foreach (var guard in forge.Diagnostics) guards[guard.Key] = guards.GetValueOrDefault(guard.Key) + guard.Value;
				entries.Add(new { guid = definition.Hash, originalName = definition.Name, originalPath = definition.FileName, actualOutputPath = relative,
					status = empty ? "empty" : "exported", canonical, structIndex = definition.StructIndex, variant = definition.VariantIndex,
					recordSize = definition.RecordSize, guards = new Dictionary<string, int>(forge.Diagnostics) });
				if (seen.Count % ProgressInterval == 0) Console.WriteLine($"Exported {seen.Count}/{forge.RecordDefinitionCount} records");
			}
			forge.BaseStream.Position = 0;
			var sourceHash = Convert.ToHexString(SHA256.HashData(forge.BaseStream)).ToLowerInvariant();
			var manifest = new { schema = 1, toolVersion = ToolVersion, complete = true, expectedRecords = forge.RecordDefinitionCount,
				exportedRecords = seen.Count, emptyRecords, errors = 0, truncations = 0, sourceSize = forge.BaseStream.Length,
				sourceSha256 = sourceHash, guards, records = entries };
			var temporary = manifestPath + ".tmp";
			File.WriteAllText(temporary, JsonSerializer.Serialize(manifest));
			File.Move(temporary, manifestPath);
			Console.WriteLine($"Completed {seen.Count} records; {emptyRecords} structurally empty; manifest: {manifestPath}");
		}

		public static bool HasErrors(XElement root) => root.DescendantsAndSelf().Any(node => node.Name.LocalName == "Error" ||
			node.Attributes().Any(attribute => IsErrorValue(attribute.Value)) ||
			node.Nodes().OfType<XText>().Any(text => IsErrorValue(text.Value.Trim())));

		private static bool IsErrorValue(string value) => value == "TBC" || value.StartsWith("Error reading ", StringComparison.Ordinal) ||
			value.StartsWith("Unhandled Type ", StringComparison.Ordinal);

		public static string SafePath(string directory, string relative)
		{
			var segments = relative.Replace('\\', '/').Split('/');
			if (Path.IsPathRooted(relative) || segments.Any(segment => segment.Length == 0 || segment == "." || segment == ".." ||
				segment.IndexOfAny(Path.GetInvalidFileNameChars()) >= 0 || segment.EndsWith('.') || segment.EndsWith(' ')))
				throw new InvalidDataException("Unsafe export path: " + relative);
			var root = Path.GetFullPath(directory) + Path.DirectorySeparatorChar;
			var result = Path.GetFullPath(Path.Combine(directory, Path.Combine(segments)));
			if (!result.StartsWith(root, StringComparison.OrdinalIgnoreCase)) throw new InvalidDataException("Path traversal");
			return result;
		}
	}
}