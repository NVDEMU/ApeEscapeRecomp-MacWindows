package com.nvd123.apeescape;

import android.app.Activity;
import android.content.Intent;
import android.database.Cursor;
import android.net.Uri;
import android.os.Bundle;
import android.provider.OpenableColumns;
import android.view.Gravity;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;
import android.widget.Toast;

import java.io.File;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/** Minimal native Android setup screen for the experimental playable build. */
public final class MainActivity extends Activity {
    private static final int REQUEST_CHD = 4107;
    private static final String PREFS = "android_setup";
    private static final String DISC_KEY = "disc_path";

    private final ExecutorService importer = Executors.newSingleThreadExecutor();
    private TextView status;
    private Button chooseButton;
    private Button playButton;

    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);
        buildLayout();
        try {
            copyBundledAssets("");
        } catch (IOException exception) {
            status.setText("Could not prepare the bundled game files:\n" + exception.getMessage());
            chooseButton.setEnabled(false);
            playButton.setEnabled(false);
            return;
        }
        refreshSelectedDisc();
    }

    private void buildLayout() {
        LinearLayout content = new LinearLayout(this);
        content.setOrientation(LinearLayout.VERTICAL);
        content.setGravity(Gravity.CENTER_HORIZONTAL);
        int pad = dp(24);
        content.setPadding(pad, pad, pad, pad);

        TextView title = new TextView(this);
        title.setText("Ape Escape Recompiled");
        title.setTextSize(27);
        title.setGravity(Gravity.CENTER);
        title.setPadding(0, 0, 0, dp(14));
        content.addView(title, new LinearLayout.LayoutParams(-1, -2));

        TextView description = new TextView(this);
        description.setText(
            "Experimental Android build\n\n" +
            "Select your own Ape Escape USA CHD file, then start the game. " +
            "The first version is designed for a Bluetooth or USB game controller. " +
            "Touchscreen controls are not implemented yet.\n\n" +
            "The app does not include the commercial game image."
        );
        description.setTextSize(16);
        description.setPadding(0, 0, 0, dp(20));
        content.addView(description, new LinearLayout.LayoutParams(-1, -2));

        chooseButton = new Button(this);
        chooseButton.setText("Choose Ape Escape CHD");
        chooseButton.setOnClickListener(view -> chooseDisc());
        content.addView(chooseButton, new LinearLayout.LayoutParams(-1, -2));

        playButton = new Button(this);
        playButton.setText("Play Ape Escape");
        playButton.setOnClickListener(view -> launchGame());
        LinearLayout.LayoutParams playParams = new LinearLayout.LayoutParams(-1, -2);
        playParams.topMargin = dp(8);
        content.addView(playButton, playParams);

        status = new TextView(this);
        status.setTextSize(14);
        status.setPadding(0, dp(16), 0, 0);
        content.addView(status, new LinearLayout.LayoutParams(-1, -2));

        ScrollView scroll = new ScrollView(this);
        scroll.addView(content);
        setContentView(scroll);
    }

    private int dp(int value) {
        return Math.round(value * getResources().getDisplayMetrics().density);
    }

    private void chooseDisc() {
        Intent intent = new Intent(Intent.ACTION_OPEN_DOCUMENT);
        intent.addCategory(Intent.CATEGORY_OPENABLE);
        intent.setType("*/*");
        startActivityForResult(intent, REQUEST_CHD);
    }

    @Override
    protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        super.onActivityResult(requestCode, resultCode, data);
        if (requestCode != REQUEST_CHD || resultCode != RESULT_OK ||
            data == null || data.getData() == null) return;

        Uri uri = data.getData();
        String name = displayName(uri);
        if (!name.toLowerCase(java.util.Locale.ROOT).endsWith(".chd")) {
            Toast.makeText(this, "This early build currently accepts .chd images.", Toast.LENGTH_LONG).show();
            return;
        }

        status.setText("Importing " + name + "… Keep the app open while it copies.");
        chooseButton.setEnabled(false);
        playButton.setEnabled(false);
        importer.execute(() -> {
            File partial = null;
            try (InputStream input = getContentResolver().openInputStream(uri)) {
                if (input == null) throw new IOException("Android could not open the selected file.");
                File directory = getExternalFilesDir("apeescape");
                if (directory == null) throw new IOException("App storage is unavailable.");
                if (!directory.exists() && !directory.mkdirs()) {
                    throw new IOException("Could not create the game-data directory.");
                }
                File target = new File(directory, "Ape Escape USA.chd");
                partial = new File(directory, "Ape Escape USA.chd.partial");
                try (OutputStream output = new FileOutputStream(partial)) {
                    byte[] buffer = new byte[1024 * 256];
                    int count;
                    while ((count = input.read(buffer)) != -1) output.write(buffer, 0, count);
                    output.flush();
                }
                if (target.exists() && !target.delete()) {
                    throw new IOException("Could not replace the previous CHD import.");
                }
                if (!partial.renameTo(target)) throw new IOException("Could not finish importing the CHD.");
                getSharedPreferences(PREFS, MODE_PRIVATE).edit()
                    .putString(DISC_KEY, target.getAbsolutePath()).apply();
                runOnUiThread(() -> {
                    status.setText("Game image ready: " + name);
                    chooseButton.setEnabled(true);
                    playButton.setEnabled(true);
                });
            } catch (Exception exception) {
                if (partial != null && partial.exists()) partial.delete();
                runOnUiThread(() -> {
                    status.setText("Game import failed: " + exception.getMessage());
                    chooseButton.setEnabled(true);
                    playButton.setEnabled(false);
                });
            }
        });
    }

    private String displayName(Uri uri) {
        try (Cursor cursor = getContentResolver().query(
                uri, new String[] { OpenableColumns.DISPLAY_NAME }, null, null, null)) {
            if (cursor != null && cursor.moveToFirst()) {
                int index = cursor.getColumnIndex(OpenableColumns.DISPLAY_NAME);
                if (index >= 0) {
                    String name = cursor.getString(index);
                    if (name != null && !name.isEmpty()) return name;
                }
            }
        } catch (Exception ignored) {
            // Fall through if document metadata is unavailable.
        }
        String path = uri.getLastPathSegment();
        return path == null ? "game.chd" : path;
    }

    private void refreshSelectedDisc() {
        String path = getSharedPreferences(PREFS, MODE_PRIVATE).getString(DISC_KEY, null);
        boolean ready = path != null && new File(path).isFile();
        playButton.setEnabled(ready);
        status.setText(ready
            ? "Previously imported game image is ready."
            : "Choose your own .chd image to get started.");
    }

    private void launchGame() {
        String path = getSharedPreferences(PREFS, MODE_PRIVATE).getString(DISC_KEY, null);
        if (path == null || !new File(path).isFile()) {
            refreshSelectedDisc();
            return;
        }
        Intent intent = new Intent(this, GameActivity.class);
        intent.putExtra(GameActivity.EXTRA_DISC_PATH, path);
        startActivity(intent);
    }

    /** Copy config and mod metadata from APK assets without touching user saves. */
    private void copyBundledAssets(String relativePath) throws IOException {
        String[] children = getAssets().list(relativePath);
        if (children != null && (relativePath.isEmpty() || children.length > 0)) {
            File directory = relativePath.isEmpty() ? getFilesDir() : new File(getFilesDir(), relativePath);
            if (!directory.exists() && !directory.mkdirs()) throw new IOException("Could not create " + directory);
            for (String child : children) {
                String next = relativePath.isEmpty() ? child : relativePath + "/" + child;
                copyBundledAssets(next);
            }
            return;
        }
        if (relativePath.isEmpty()) return;
        File destination = new File(getFilesDir(), relativePath);
        if (destination.isFile()) return;
        File parent = destination.getParentFile();
        if (parent != null && !parent.exists() && !parent.mkdirs()) throw new IOException("Could not create " + parent);
        try (InputStream input = getAssets().open(relativePath);
             OutputStream output = new FileOutputStream(destination)) {
            byte[] buffer = new byte[32 * 1024];
            int count;
            while ((count = input.read(buffer)) != -1) output.write(buffer, 0, count);
        }
    }

    @Override
    protected void onDestroy() {
        importer.shutdown();
        super.onDestroy();
    }
}
