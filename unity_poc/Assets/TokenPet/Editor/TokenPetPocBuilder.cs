using System.IO;
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
            PlayerSettings.defaultScreenWidth = 512;
            PlayerSettings.defaultScreenHeight = 512;
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

            Debug.Log($"TokenPet Unity PoC built at {executable}");
        }
    }
}
