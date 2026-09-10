using System;
using System.IO;
using System.IO.Compression;
using UnityEditor;
using UnityEditor.Build;
using UnityEditor.Build.Reporting;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.SceneManagement;

namespace TokenPet.Editor
{
    [InitializeOnLoad]
    public static class TokenPetPocBuilder
    {
        private const string SceneDirectory = "Assets/TokenPet/Scenes";
        private const string ScenePath = SceneDirectory + "/TokenPetPoc.unity";

        static TokenPetPocBuilder()
        {
            EditorApplication.delayCall += EnsureScene;
        }

        private static void EnsureScene()
        {
            if (!Directory.Exists(SceneDirectory))
                Directory.CreateDirectory(SceneDirectory);

            if (!File.Exists(ScenePath))
            {
                Scene scene = EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
                EditorSceneManager.SaveScene(scene, ScenePath);
            }

            EditorBuildSettings.scenes = new[] { new EditorBuildSettingsScene(ScenePath, true) };
            ConfigurePlayer();
        }

        private static void ConfigurePlayer()
        {
            PlayerSettings.companyName = "TokenPet";
            PlayerSettings.productName = "TokenPet Unity Renderer PoC";
            PlayerSettings.defaultScreenWidth = 340;
            PlayerSettings.defaultScreenHeight = 300;
            PlayerSettings.resizableWindow = false;
            PlayerSettings.runInBackground = true;
            PlayerSettings.fullScreenMode = FullScreenMode.Windowed;
            PlayerSettings.colorSpace = ColorSpace.Linear;
            // Layered/DWM transparent windows require the legacy blit-model D3D11
            // swap chain. Flip-model swap chains are composed as opaque black.
            PlayerSettings.useFlipModelSwapchain = false;
        }

        [MenuItem("TokenPet/Build Windows PoC")]
        public static void BuildWindows()
        {
            EnsureScene();
            string outputDirectory = Path.GetFullPath(Path.Combine(Application.dataPath, "..", "Build"));
            Directory.CreateDirectory(outputDirectory);
            string executable = Path.Combine(outputDirectory, "TokenPetUnity.exe");

            BuildPlayerOptions options = new()
            {
                scenes = new[] { ScenePath },
                locationPathName = executable,
                target = BuildTarget.StandaloneWindows64,
                options = BuildOptions.None
            };
            BuildReport report = BuildPipeline.BuildPlayer(options);
            if (report.summary.result != BuildResult.Succeeded)
                throw new BuildFailedException($"TokenPet Unity build failed: {report.summary.result}");

            Debug.Log($"TokenPet Unity preview built at {executable}");
        }

        [MenuItem("TokenPet/Package Approved Windows Build")]
        public static void PackageApprovedWindowsBuild()
        {
            string outputDirectory = Path.GetFullPath(
                Path.Combine(Application.dataPath, "..", "Build"));
            string executable = Path.Combine(outputDirectory, "TokenPetUnity.exe");
            if (!File.Exists(executable))
                throw new BuildFailedException(
                    "No Windows preview build found. Run TokenPet/Build Windows PoC first.");
            PackageWindowsBuild(outputDirectory);
        }

        private static void PackageWindowsBuild(string outputDirectory)
        {
            string projectDirectory = Path.GetFullPath(Path.Combine(Application.dataPath, ".."));
            string repositoryDirectory = Path.GetFullPath(Path.Combine(projectDirectory, ".."));
            string distributionDirectory = Path.Combine(repositoryDirectory, "dist");
            Directory.CreateDirectory(distributionDirectory);

            string archiveName =
                $"TokenPetUnity-v{TokenPet.TokenPetPocBootstrap.RendererVersion}-win-x64.zip";
            string archivePath = Path.Combine(distributionDirectory, archiveName);
            if (File.Exists(archivePath))
                File.Delete(archivePath);

            string root = Path.GetFullPath(outputDirectory)
                .TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar)
                + Path.DirectorySeparatorChar;

            using FileStream archiveStream = new(archivePath, FileMode.CreateNew, FileAccess.Write);
            using ZipArchive archive = new(archiveStream, ZipArchiveMode.Create);
            foreach (string filePath in Directory.GetFiles(root, "*", SearchOption.AllDirectories))
            {
                string relativePath = filePath.Substring(root.Length).Replace('\\', '/');
                if (relativePath.IndexOf(
                        "_BurstDebugInformation_DoNotShip",
                        StringComparison.OrdinalIgnoreCase) >= 0)
                {
                    continue;
                }

                ZipArchiveEntry entry = archive.CreateEntry(
                    relativePath,
                    System.IO.Compression.CompressionLevel.Optimal);
                using Stream source = File.OpenRead(filePath);
                using Stream destination = entry.Open();
                source.CopyTo(destination);
            }

            Debug.Log($"TokenPet Unity package created at {archivePath}");
        }
    }
}
